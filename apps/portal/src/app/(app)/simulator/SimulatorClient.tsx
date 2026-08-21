'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { Send, Square, PhoneCall, PhoneOff, PhoneForwarded, Loader2, AlertCircle, Mic, MicOff, Volume2, Radio } from 'lucide-react'

interface Campaign {
  id: string
  name: string
  direction: 'inbound' | 'outbound'
  publishedVersionId: string | null
  versions?: { id: string; version: string; body: Record<string, unknown>; status: string }[]
}

type WsStatus = 'idle' | 'connecting' | 'active' | 'hangup' | 'handoff' | 'error'

interface ChatMessage {
  id: string
  role: 'ai' | 'user' | 'system'
  text: string
  stepId?: string
  turn?: number
  ttfa?: number
}

interface SlotMap {
  [key: string]: string
}

interface TurnMeta {
  turn: number
  intent: string | null
  slotsNew: SlotMap
  stepFrom: string
  stepTo: string
  nluConfidence: number
  nluTier: string
  filler: string
}

// Same-origin as the Portal page itself — the custom Next.js server
// (apps/portal/custom-server.js) proxies /ws/call to the voice worker's
// in-cluster ClusterIP, since Portal and voice run in the same k8s
// namespace and the browser has no direct route to voice's internal DNS.
function resolveVoiceWsUrl(): string {
  if (typeof window === 'undefined') return ''
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}`
}

function uid() {
  return Math.random().toString(36).slice(2)
}

// Decode base64 int16 PCM and schedule it on the AudioContext timeline
function scheduleAudioChunk(
  base64: string,
  ctx: AudioContext,
  nextPlayTimeRef: React.MutableRefObject<number>,
  onSpeakingChange: (v: boolean) => void,
  speakingTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
) {
  try {
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    const int16 = new Int16Array(bytes.buffer)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768

    console.debug('[Audio] ctx.state=%s ctx.sampleRate=%d samples=%d', ctx.state, ctx.sampleRate, float32.length)

    if (ctx.state === 'suspended') {
      void ctx.resume()
    }

    const buf = ctx.createBuffer(1, float32.length, 8000)
    buf.copyToChannel(float32, 0)
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.connect(ctx.destination)

    const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current)
    src.start(startAt)
    nextPlayTimeRef.current = startAt + buf.duration

    // Mark speaking until queue drains
    onSpeakingChange(true)
    if (speakingTimerRef.current) clearTimeout(speakingTimerRef.current)
    const drainMs = Math.max(0, (nextPlayTimeRef.current - ctx.currentTime) * 1000) + 300
    speakingTimerRef.current = setTimeout(() => onSpeakingChange(false), drainMs)
  } catch (err) {
    console.error('[Audio] scheduleAudioChunk error:', err)
  }
}

export function SimulatorClient({ campaigns }: { campaigns: Campaign[] }) {
  const [selectedId, setSelectedId] = useState<string>(campaigns[0]?.id ?? '')
  const [wsStatus, setWsStatus] = useState<WsStatus>('idle')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [slots, setSlots] = useState<SlotMap>({})
  const [turnHistory, setTurnHistory] = useState<TurnMeta[]>([])
  const [currentStep, setCurrentStep] = useState<string>('')
  const [turn, setTurn] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [audioMode, setAudioMode] = useState(false)
  const [aiSpeaking, setAiSpeaking] = useState(false)
  const [micActive, setMicActive] = useState(false)
  const [useRealTts, setUseRealTts] = useState(true)
  const [ttsEngine, setTtsEngine] = useState<string>('xkiro')
  const [switchingEngine, setSwitchingEngine] = useState(false)
  const [hasSpeechRecognition, setHasSpeechRecognition] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const pendingBeatRef = useRef<string>('')
  const pendingTurnRef = useRef<number>(0)
  const pendingStepRef = useRef<string>('')
  const pendingTtfaRef = useRef<number | undefined>(undefined)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Audio playback
  const audioCtxRef = useRef<AudioContext | null>(null)
  const nextPlayTimeRef = useRef<number>(0)
  const speakingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Mic (Web Speech API)
  const recognitionRef = useRef<unknown>(null)
  const micAutoRestartRef = useRef(false)

  useEffect(() => {
    setHasSpeechRecognition('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)
    void fetch('/api/v1/settings/tts').then(async (r) => {
      if (r.ok) {
        const d = await r.json() as { engine?: string }
        if (d.engine) setTtsEngine(d.engine)
      }
    })
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  function flushPendingBeat() {
    const text = pendingBeatRef.current.trim()
    if (!text) return
    setMessages((prev) => [
      ...prev,
      {
        id: uid(),
        role: 'ai',
        text,
        stepId: pendingStepRef.current,
        turn: pendingTurnRef.current,
        ttfa: pendingTtfaRef.current,
      },
    ])
    pendingBeatRef.current = ''
    pendingTtfaRef.current = undefined
  }

  const handleMessage = useCallback((raw: unknown) => {
    const msg = raw as Record<string, unknown>
    const event = msg.event as string

    if (event === 'beat') {
      const text = msg.text as string
      const pauseMs = (msg.pause_ms as number) ?? 0
      const t = (msg.turn as number) ?? 0
      const stepId = (msg.step_id as string) ?? ''
      const ttfa = msg.ttfa_ms as number | undefined

      setCurrentStep(stepId)
      setTurn(t)

      if (pendingTurnRef.current !== t && pendingBeatRef.current) {
        flushPendingBeat()
      }

      pendingTurnRef.current = t
      pendingStepRef.current = stepId
      if (ttfa !== undefined && pendingTtfaRef.current === undefined) {
        pendingTtfaRef.current = ttfa
      }

      pendingBeatRef.current += (pendingBeatRef.current ? ' ' : '') + text
      if (pauseMs >= 300) {
        flushPendingBeat()
      }

    } else if (event === 'audio_chunk') {
      setAudioMode(true)
      const ctx = audioCtxRef.current
      if (ctx) {
        scheduleAudioChunk(
          msg.data as string,
          ctx,
          nextPlayTimeRef,
          setAiSpeaking,
          speakingTimerRef,
        )
      }

    } else if (event === 'turn_meta') {
      const meta: TurnMeta = {
        turn: (msg.turn as number) ?? 0,
        intent: (msg.intent as string | null) ?? null,
        slotsNew: (msg.slots_new as SlotMap) ?? {},
        stepFrom: (msg.step_from as string) ?? '',
        stepTo: (msg.step_to as string) ?? '',
        nluConfidence: (msg.nlu_confidence as number) ?? 0,
        nluTier: (msg.nlu_tier as string) ?? '',
        filler: (msg.filler as string) ?? '',
      }
      setTurnHistory((prev) => [...prev, meta])
      if (Object.keys(meta.slotsNew).length > 0) {
        setSlots((prev) => ({ ...prev, ...meta.slotsNew }))
      }

    } else if (event === 'hangup') {
      flushPendingBeat()
      setWsStatus('hangup')
      setAiSpeaking(false)
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: 'system', text: '— Cuộc gọi kết thúc (hangup) —' },
      ])
      wsRef.current?.close()

    } else if (event === 'handoff') {
      flushPendingBeat()
      setWsStatus('handoff')
      setAiSpeaking(false)
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: 'system', text: '— Chuyển máy sang nhân viên (handoff) —' },
      ])
      wsRef.current?.close()

    } else if (event === 'error') {
      setErrorMsg((msg.message as string) ?? 'Unknown error')
      setWsStatus('error')
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  function startSimulation() {
    const selectedCampaign = campaigns.find((c) => c.id === selectedId)
    const publishedVersion =
      selectedCampaign?.versions?.find((v) => v.id === selectedCampaign.publishedVersionId) ??
      selectedCampaign?.versions?.[0]
    if (!publishedVersion) return

    setMessages([])
    setSlots({})
    setCurrentStep('')
    setTurn(0)
    setErrorMsg('')
    setAudioMode(false)
    setAiSpeaking(false)
    setTurnHistory([])
    pendingBeatRef.current = ''

    // Init AudioContext on user gesture (required by browser autoplay policy)
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext({ sampleRate: 8000 })
    }
    if (audioCtxRef.current.state === 'suspended') {
      void audioCtxRef.current.resume()
    }
    nextPlayTimeRef.current = 0

    setWsStatus('connecting')

    const ws = new WebSocket(`${resolveVoiceWsUrl()}/ws/call`)
    wsRef.current = ws

    ws.onopen = () => {
      setWsStatus('active')
      ws.send(JSON.stringify({
        event: 'start',
        session_id: `sim-${uid()}`,
        campaign_id: selectedCampaign?.id ?? '',
        script_version_id: publishedVersion.id,
        direction: selectedCampaign?.direction ?? 'inbound',
        caller_number: null,
        script: publishedVersion.body,
        use_real_tts: useRealTts,
      }))
      inputRef.current?.focus()
    }

    ws.onmessage = (e: MessageEvent<string>) => {
      try {
        handleMessage(JSON.parse(e.data) as unknown)
      } catch {
        // ignore malformed frames
      }
    }

    ws.onerror = () => {
      setErrorMsg('Không kết nối được voice worker. Kiểm tra voice worker đang chạy.')
      setWsStatus('error')
    }

    ws.onclose = () => {
      if (wsStatus === 'active') setWsStatus('hangup')
    }
  }

  function stopSimulation() {
    stopMic()
    flushPendingBeat()
    wsRef.current?.close()
    setWsStatus('hangup')
    setAiSpeaking(false)
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: 'system', text: '— Dừng giả lập —' },
    ])
  }

  function sendUtteranceText(text: string) {
    if (!text || wsRef.current?.readyState !== WebSocket.OPEN) return
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: 'user', text, turn: turn + 1 },
    ])
    wsRef.current.send(JSON.stringify({ event: 'utterance', text, confidence: 1.0 }))
  }

  function sendUtterance() {
    const text = input.trim()
    if (!text || wsStatus !== 'active') return
    sendUtteranceText(text)
    setInput('')
  }

  function startMicSession() {
    const SR =
      (window as unknown as Record<string, unknown>).SpeechRecognition ??
      (window as unknown as Record<string, unknown>).webkitSpeechRecognition
    if (!SR) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const recognition = new (SR as new () => any)()

    recognition.lang = 'vi-VN'
    recognition.continuous = false
    recognition.interimResults = false

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (e: any) => {
      const transcript = (e.results[0][0].transcript as string).trim()
      if (transcript) sendUtteranceText(transcript)
    }

    recognition.onend = () => {
      if (micAutoRestartRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
        setTimeout(() => startMicSession(), 200)
      } else {
        micAutoRestartRef.current = false
        setMicActive(false)
      }
    }

    recognitionRef.current = recognition
    recognition.start()
  }

  function toggleMic() {
    if (micActive) {
      stopMic()
    } else {
      micAutoRestartRef.current = true
      startMicSession()
      setMicActive(true)
    }
  }

  function stopMic() {
    micAutoRestartRef.current = false
    ;(recognitionRef.current as { stop?: () => void } | null)?.stop?.()
    setMicActive(false)
  }

  const selectedCampaign = campaigns.find((c) => c.id === selectedId)
  const publishedVersion =
    selectedCampaign?.versions?.find((v) => v.id === selectedCampaign.publishedVersionId) ??
    selectedCampaign?.versions?.[0]

  const isRunning = wsStatus === 'active'
  const isDone = wsStatus === 'hangup' || wsStatus === 'handoff'

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)]">
      {/* ── Left: Chat ──────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3.5 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <select
              className="input py-1.5 text-sm flex-1"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              disabled={isRunning}
            >
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            {publishedVersion && (
              <span className="text-xs text-[var(--color-text-muted)] whitespace-nowrap">
                v{publishedVersion.version}
              </span>
            )}
            {/* TTS engine switcher */}
            <select
              disabled={isRunning || switchingEngine}
              value={ttsEngine}
              onChange={(e) => {
                const engine = e.target.value
                setSwitchingEngine(true)
                void (async () => {
                  try {
                    const cur = await fetch('/api/v1/settings/tts').then((r) => r.ok ? r.json() as Promise<Record<string, unknown>> : {})
                    await fetch('/api/v1/settings/tts', {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ ...cur, engine }),
                    })
                    setTtsEngine(engine)
                  } finally {
                    setSwitchingEngine(false)
                  }
                })()
              }}
              className={[
                'text-xs border rounded-lg px-2 py-1 bg-white text-[var(--color-text)] border-[var(--color-border)]',
                'focus:outline-none focus:border-[var(--color-accent)]',
                (isRunning || switchingEngine) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
              ].join(' ')}
              title="Chọn TTS engine — lưu ngay vào Settings"
            >
              <option value="xkiro">xKiro (cloud, mặc định)</option>
              <option value="edge-tts">edge-tts (dự phòng, miễn phí)</option>
              <option value="disabled">Tắt TTS</option>
            </select>

            {/* LLM hiện cố định qua xKiro (services/voice/api/config.py — LLM_MODEL),
                không đổi được theo phiên như trước (thời Ollama local) nữa. */}
            <span
              className="text-xs text-[var(--color-text-muted)] px-2 py-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] whitespace-nowrap"
              title="Model LLM cấu hình cố định ở server (xKiro), không đổi qua Simulator được"
            >
              qwen3.5-flash (xKiro)
            </span>

            {/* Real TTS toggle */}
            <button
              type="button"
              onClick={() => !isRunning && setUseRealTts((v) => !v)}
              title={useRealTts ? 'Real TTS bật — gửi audio' : 'Text mode — chỉ nhận beat text'}
              className={[
                'inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium border transition-colors whitespace-nowrap',
                useRealTts
                  ? 'bg-[oklch(55%_0.18_250)] text-white border-[oklch(55%_0.18_250)]'
                  : 'bg-white text-[var(--color-text-muted)] border-[var(--color-border)] hover:border-[var(--color-accent)]',
                isRunning ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
              ].join(' ')}
            >
              <Radio className="w-3 h-3" />
              {useRealTts ? 'Audio' : 'Text'}
            </button>
            {audioMode && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-[oklch(50%_0.16_250)] bg-[oklch(95%_0.03_250)] px-2 py-0.5 rounded-full whitespace-nowrap">
                <Volume2 className="w-3 h-3" />
                Audio
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {!isRunning && !isDone && (
              <button
                onClick={startSimulation}
                disabled={!publishedVersion || wsStatus === 'connecting'}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[oklch(55%_0.16_145)] text-white text-sm font-medium hover:bg-[oklch(48%_0.16_145)] disabled:opacity-40 transition-colors"
              >
                {wsStatus === 'connecting' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <PhoneCall className="w-3.5 h-3.5" />
                )}
                Bắt đầu
              </button>
            )}
            {isRunning && (
              <button
                onClick={stopSimulation}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[oklch(55%_0.18_25)] text-white text-sm font-medium hover:bg-[oklch(48%_0.18_25)] transition-colors"
              >
                <Square className="w-3.5 h-3.5" />
                Dừng
              </button>
            )}
            {isDone && (
              <button
                onClick={startSimulation}
                disabled={!publishedVersion}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-sm font-medium hover:bg-[var(--color-surface)] transition-colors"
              >
                <PhoneCall className="w-3.5 h-3.5" />
                Chạy lại
              </button>
            )}

            <WsStatusBadge status={wsStatus} />
          </div>
        </div>

        {/* AI Speaking indicator (audio mode only) */}
        {audioMode && aiSpeaking && (
          <div className="flex items-center gap-2 px-5 py-2 bg-[oklch(96%_0.02_250)] border-b border-[oklch(88%_0.04_250)]">
            <SpeakingWave />
            <span className="text-xs text-[oklch(50%_0.16_250)]">AI đang nói...</span>
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {wsStatus === 'idle' && (
            <div className="flex flex-col items-center justify-center h-full text-center text-[var(--color-text-muted)]">
              <PhoneCall className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm">Chọn campaign và nhấn <strong>Bắt đầu</strong> để giả lập cuộc gọi</p>
              {!publishedVersion && (
                <p className="text-xs mt-1 text-[oklch(55%_0.18_25)]">Campaign này chưa có version nào được publish</p>
              )}
            </div>
          )}
          {wsStatus === 'error' && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-[oklch(97%_0.02_25)] border border-[oklch(88%_0.05_25)] text-sm text-[oklch(45%_0.18_25)]">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              {errorMsg}
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>

        {/* Input */}
        <div className="px-5 py-3 border-t border-[var(--color-border)]">
          <div className="flex gap-2">
            {hasSpeechRecognition && (
              <button
                onClick={toggleMic}
                disabled={!isRunning}
                title={micActive ? 'Tắt mic' : 'Bật mic (vi-VN)'}
                className={[
                  'px-3 py-2 rounded-lg transition-colors disabled:opacity-40',
                  micActive
                    ? 'bg-[oklch(55%_0.18_25)] text-white animate-pulse'
                    : 'border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface)]',
                ].join(' ')}
              >
                {micActive ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
            )}
            <input
              ref={inputRef}
              type="text"
              className="input flex-1"
              placeholder={isRunning ? 'Nhập hoặc dùng mic...' : 'Chờ bắt đầu...'}
              value={input}
              disabled={!isRunning}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') sendUtterance() }}
            />
            <button
              onClick={sendUtterance}
              disabled={!isRunning || !input.trim()}
              className="px-3 py-2 rounded-lg bg-[var(--color-accent)] text-white disabled:opacity-40 transition-colors hover:bg-[var(--color-accent-hover)]"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] mt-1.5">
            Bạn đang đóng vai <strong>khách hàng</strong>.
            {hasSpeechRecognition && ' Nhấn mic để nói tiếng Việt.'}
          </p>
        </div>
      </div>

      {/* ── Right: Workflow ─────────────────────────────────── */}
      <div className="w-72 shrink-0 flex flex-col gap-3 overflow-y-auto">
        {/* FSM State */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-3">Trạng thái</p>
          <div className="space-y-2">
            <MetaRow label="Turn" value={turn > 0 ? String(turn) : '—'} />
            <MetaRow label="Step" value={currentStep || '—'} mono />
            <MetaRow label="WS" value={wsStatus} />
            <MetaRow label="Mode" value={audioMode ? 'Audio' : 'Text'} />
          </div>
        </div>

        {/* NLU Turn History */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4 flex-1 min-h-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-3">NLU / FSM Workflow</p>
          {turnHistory.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">Chưa có turn nào</p>
          ) : (
            <div className="space-y-3 overflow-y-auto max-h-64">
              {turnHistory.slice(-8).map((m) => (
                <TurnMetaCard key={m.turn} meta={m} />
              ))}
            </div>
          )}
        </div>

        {/* Slots */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-3">Slots</p>
          {Object.keys(slots).filter((k) => !k.startsWith('today') && !k.startsWith('tomorrow')).length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">Chưa có slot nào</p>
          ) : (
            <div className="space-y-1.5">
              {Object.entries(slots)
                .filter(([k]) => !k.startsWith('today') && !k.startsWith('tomorrow'))
                .map(([k, v]) => (
                  <div key={k} className="flex items-start gap-1.5 text-xs">
                    <span className="font-mono text-[var(--color-text-muted)] shrink-0">{k}:</span>
                    <span className="text-[var(--color-text)] break-all font-medium">{v}</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SpeakingWave() {
  return (
    <span className="inline-flex items-end gap-[2px] h-4">
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className="w-[3px] rounded-full bg-[oklch(50%_0.16_250)]"
          style={{
            height: `${[40, 70, 100, 60][i]}%`,
            animation: `speakPulse 0.8s ease-in-out ${i * 0.15}s infinite alternate`,
          }}
        />
      ))}
      <style>{`
        @keyframes speakPulse {
          from { transform: scaleY(0.4); }
          to   { transform: scaleY(1); }
        }
      `}</style>
    </span>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'system') {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-[var(--color-text-muted)] bg-[var(--color-surface)] px-3 py-1 rounded-full">
          {message.text}
        </span>
      </div>
    )
  }

  const isAI = message.role === 'ai'

  return (
    <div className={['flex', isAI ? 'justify-start' : 'justify-end'].join(' ')}>
      <div className={[
        'max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
        isAI
          ? 'bg-[var(--color-surface)] text-[var(--color-text)] rounded-tl-sm'
          : 'bg-[var(--color-accent)] text-white rounded-tr-sm',
      ].join(' ')}>
        <p>{message.text}</p>
        {isAI && (message.stepId || message.ttfa !== undefined) && (
          <p className="text-xs mt-1 font-mono opacity-60">
            {message.stepId && <span>{message.stepId}</span>}
            {message.ttfa !== undefined && (
              <span className={[
                'ml-1',
                message.ttfa < 500 ? 'text-[oklch(45%_0.16_145)]' :
                message.ttfa < 1000 ? 'text-[oklch(52%_0.18_50)]' :
                'text-[oklch(50%_0.18_25)]',
              ].join('')}>
                {' · '}{message.ttfa}ms
              </span>
            )}
          </p>
        )}
      </div>
    </div>
  )
}

function TurnMetaCard({ meta }: { meta: TurnMeta }) {
  const tierColor: Record<string, string> = {
    confident: 'text-[oklch(45%_0.16_145)] bg-[oklch(96%_0.03_145)]',
    clarify:   'text-[oklch(52%_0.18_50)]  bg-[oklch(96%_0.03_50)]',
    handoff:   'text-[oklch(50%_0.18_25)]  bg-[oklch(97%_0.02_25)]',
  }
  const confColor =
    meta.nluConfidence >= 0.8 ? 'text-[oklch(45%_0.16_145)]' :
    meta.nluConfidence >= 0.6 ? 'text-[oklch(52%_0.18_50)]' :
    'text-[oklch(50%_0.18_25)]'

  return (
    <div className="text-xs border border-[var(--color-border)] rounded-xl p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[var(--color-text-muted)]">Turn {meta.turn}</span>
        {meta.nluTier && (
          <span className={['px-1.5 py-0.5 rounded-full font-medium text-[10px]', tierColor[meta.nluTier] ?? 'text-[var(--color-text-muted)]'].join(' ')}>
            {meta.nluTier}
          </span>
        )}
      </div>

      {/* Intent */}
      <div className="flex items-center gap-1.5">
        <span className="text-[var(--color-text-muted)] shrink-0">intent:</span>
        <span className="font-mono font-semibold text-[var(--color-text)] truncate">
          {meta.intent ?? <span className="opacity-40">null</span>}
        </span>
        {meta.nluConfidence > 0 && (
          <span className={['ml-auto shrink-0 font-mono', confColor].join(' ')}>
            {(meta.nluConfidence * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* Step transition */}
      <div className="flex items-center gap-1 flex-wrap">
        <span className="font-mono bg-[var(--color-surface)] px-1.5 py-0.5 rounded text-[10px] text-[var(--color-text-muted)]">
          {meta.stepFrom}
        </span>
        {meta.stepTo !== meta.stepFrom && (
          <>
            <span className="text-[var(--color-text-muted)]">→</span>
            <span className="font-mono bg-[oklch(96%_0.03_145)] px-1.5 py-0.5 rounded text-[10px] text-[oklch(45%_0.16_145)]">
              {meta.stepTo}
            </span>
          </>
        )}
      </div>

      {/* New slots */}
      {Object.keys(meta.slotsNew).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {Object.entries(meta.slotsNew).map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-0.5 bg-[oklch(96%_0.03_250)] text-[oklch(45%_0.16_250)] px-1.5 py-0.5 rounded-full text-[10px]">
              <span className="opacity-60">{k}=</span>{v}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function WsStatusBadge({ status }: { status: WsStatus }) {
  const map: Record<WsStatus, { label: string; color: string; icon?: React.ReactNode }> = {
    idle:       { label: 'Chờ',       color: 'text-[var(--color-text-muted)]' },
    connecting: { label: 'Đang kết nối...', color: 'text-[oklch(60%_0.15_250)]', icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    active:     { label: 'Đang gọi',  color: 'text-[oklch(50%_0.16_145)]', icon: <PhoneCall className="w-3 h-3" /> },
    hangup:     { label: 'Kết thúc',  color: 'text-[var(--color-text-muted)]', icon: <PhoneOff className="w-3 h-3" /> },
    handoff:    { label: 'Chuyển máy', color: 'text-[oklch(55%_0.18_50)]', icon: <PhoneForwarded className="w-3 h-3" /> },
    error:      { label: 'Lỗi',       color: 'text-[oklch(50%_0.18_25)]', icon: <AlertCircle className="w-3 h-3" /> },
  }
  const { label, color, icon } = map[status]
  return (
    <span className={['inline-flex items-center gap-1 text-xs font-medium', color].join(' ')}>
      {icon}
      {label}
    </span>
  )
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-[var(--color-text-muted)] shrink-0">{label}</span>
      <span className={['text-xs text-[var(--color-text)] text-right break-all', mono ? 'font-mono' : ''].join(' ')}>
        {value}
      </span>
    </div>
  )
}
