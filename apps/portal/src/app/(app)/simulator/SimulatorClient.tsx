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

const VOICE_WS_URL =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_VOICE_WS_URL ?? 'ws://localhost:8000')
    : 'ws://localhost:8000'

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
  const [currentStep, setCurrentStep] = useState<string>('')
  const [turn, setTurn] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [audioMode, setAudioMode] = useState(false)
  const [aiSpeaking, setAiSpeaking] = useState(false)
  const [micActive, setMicActive] = useState(false)
  const [useRealTts, setUseRealTts] = useState(true)
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
    // Detect speech recognition support client-side only (avoids SSR hydration mismatch)
    setHasSpeechRecognition('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)
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

    const ws = new WebSocket(`${VOICE_WS_URL}/ws/call`)
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
            {/* Real TTS toggle */}
            <button
              type="button"
              onClick={() => !isRunning && setUseRealTts((v) => !v)}
              title={useRealTts ? 'Real TTS bật — dùng ElevenLabs/gwen-tts' : 'Text mode — chỉ nhận beat text'}
              className={[
                'inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium border transition-colors whitespace-nowrap',
                useRealTts
                  ? 'bg-[oklch(55%_0.18_250)] text-white border-[oklch(55%_0.18_250)]'
                  : 'bg-white text-[var(--color-text-muted)] border-[var(--color-border)] hover:border-[var(--color-accent)]',
                isRunning ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
              ].join(' ')}
            >
              <Radio className="w-3 h-3" />
              {useRealTts ? 'Real TTS' : 'Text mode'}
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

      {/* ── Right: Metadata ─────────────────────────────────── */}
      <div className="w-64 shrink-0 flex flex-col gap-4">
        {/* FSM State */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-3">Trạng thái FSM</p>
          <div className="space-y-2">
            <MetaRow label="Turn" value={turn > 0 ? String(turn) : '—'} />
            <MetaRow label="Step hiện tại" value={currentStep || '—'} mono />
            <MetaRow label="Kết nối" value={wsStatus} />
            <MetaRow label="Chế độ" value={audioMode ? '🔊 Audio' : '💬 Text'} />
          </div>
        </div>

        {/* Slots */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-3">Slots đã thu thập</p>
          {Object.keys(slots).length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">Chưa có slot nào</p>
          ) : (
            <div className="space-y-1.5">
              {Object.entries(slots).map(([k, v]) => (
                <div key={k} className="flex items-start gap-1.5 text-xs">
                  <span className="font-mono text-[var(--color-text-muted)] shrink-0">{k}:</span>
                  <span className="text-[var(--color-text)] break-all">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Hint */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-2">Hướng dẫn</p>
          <ul className="text-xs text-[var(--color-text-muted)] space-y-1.5 list-none">
            {audioMode ? (
              <>
                <li>• <strong>Real TTS</strong> bật — ElevenLabs/gwen-tts đang chạy</li>
                <li>• Audio phát qua loa của trình duyệt</li>
                <li>• Dùng mic để nói tiếng Việt tự nhiên</li>
              </>
            ) : (
              <>
                <li>• <strong>Text mode</strong> — nhận beat text, không audio</li>
                <li>• Bật toggle <strong>Real TTS</strong> trên đầu để nghe ElevenLabs</li>
                <li>• Cần <code className="bg-[var(--color-surface)] px-1 rounded">ELEVENLABS_API_KEY</code> trong .env</li>
              </>
            )}
          </ul>
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
          <p className="text-xs mt-1 opacity-50 font-mono">
            {message.stepId && `step: ${message.stepId}`}
            {message.ttfa !== undefined && ` · TTFA: ${message.ttfa}ms`}
          </p>
        )}
      </div>
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
