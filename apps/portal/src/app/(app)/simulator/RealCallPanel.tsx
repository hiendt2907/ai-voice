'use client'

import { useEffect, useRef, useState } from 'react'
import { PhoneCall, Loader2, AlertCircle, Radio } from 'lucide-react'

interface WatchMessage {
  event: string
  agent_text?: string
  intent?: string | null
  step_from?: string
  step_to?: string
  [key: string]: unknown
}

interface TranscriptLine {
  id: string
  role: 'ai' | 'system'
  text: string
  meta?: string
}

function uid() {
  return Math.random().toString(36).slice(2)
}

function normalizePhone(input: string): string {
  return input.replace(/[^\d+]/g, '')
}

export function RealCallPanel() {
  const [phone, setPhone] = useState('')
  const [dialing, setDialing] = useState(false)
  const [dialError, setDialError] = useState('')
  const [watching, setWatching] = useState(false)
  const [lines, setLines] = useState<TranscriptLine[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [lines])

  useEffect(() => () => wsRef.current?.close(), [])

  function connectWatch(normalizedPhone: string) {
    wsRef.current?.close()
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${scheme}//${window.location.host}/ws/watch/${encodeURIComponent(normalizedPhone)}`)
    wsRef.current = ws

    ws.onopen = () => {
      setWatching(true)
      setLines((prev) => [...prev, { id: uid(), role: 'system', text: `Đang theo dõi cuộc gọi tới ${normalizedPhone}...` }])
    }
    ws.onmessage = (e: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(e.data) as WatchMessage
        if (msg.event === 'turn_trace') {
          if (msg.agent_text) {
            setLines((prev) => [...prev, {
              id: uid(), role: 'ai', text: msg.agent_text as string,
              meta: [msg.step_to, msg.intent].filter(Boolean).join(' · '),
            }])
          }
        } else if (msg.event === 'hangup' || msg.event === 'handoff') {
          setLines((prev) => [...prev, { id: uid(), role: 'system', text: `— Cuộc gọi kết thúc (${msg.event}) —` }])
          setWatching(false)
          ws.close()
        }
      } catch {
        // ignore malformed frames
      }
    }
    ws.onerror = () => {
      setLines((prev) => [...prev, { id: uid(), role: 'system', text: 'Mất kết nối theo dõi.' }])
    }
    ws.onclose = () => setWatching(false)
  }

  async function handleDial() {
    const normalized = normalizePhone(phone)
    if (!normalized) return
    setDialing(true)
    setDialError('')
    setLines([])
    try {
      const res = await fetch('/api/v1/voip24h/dial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: normalized }),
      })
      const data = await res.json() as { message?: string }
      if (!res.ok) {
        setDialError(data.message ?? 'Gọi thất bại')
        return
      }
      setLines([{ id: uid(), role: 'system', text: `Đã gửi lệnh gọi tới ${normalized} — chờ bắt máy...` }])
      connectWatch(normalized)
    } catch (err) {
      setDialError(err instanceof Error ? err.message : 'Gọi thất bại')
    } finally {
      setDialing(false)
    }
  }

  return (
    <div className="flex flex-col h-full rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <input
          type="tel"
          className="input flex-1 py-1.5 text-sm"
          placeholder="Số điện thoại cần gọi test, vd 0901234567"
          value={phone}
          disabled={dialing}
          onChange={(e) => setPhone(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void handleDial() }}
        />
        <button
          onClick={() => void handleDial()}
          disabled={dialing || !phone.trim()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[oklch(55%_0.16_145)] text-white text-sm font-medium hover:bg-[oklch(48%_0.16_145)] disabled:opacity-40 transition-colors whitespace-nowrap"
        >
          {dialing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PhoneCall className="w-3.5 h-3.5" />}
          Gọi
        </button>
        {watching && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-[oklch(50%_0.16_145)] whitespace-nowrap">
            <Radio className="w-3 h-3" />
            Live
          </span>
        )}
      </div>

      {dialError && (
        <div className="flex items-start gap-2 mx-5 mt-3 p-3 rounded-lg bg-[oklch(97%_0.02_25)] border border-[oklch(88%_0.05_25)] text-sm text-[oklch(45%_0.18_25)]">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {dialError}
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {lines.length === 0 && !dialError && (
          <div className="flex flex-col items-center justify-center h-full text-center text-[var(--color-text-muted)]">
            <PhoneCall className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">Nhập số điện thoại và bấm <strong>Gọi</strong> để đặt cuộc gọi thật qua voip24h</p>
            <p className="text-xs mt-1">Softphone trên Mac phải đang chạy và đăng ký sẵn với voip24h</p>
          </div>
        )}
        {lines.map((l) => (
          <div key={l.id} className={l.role === 'system' ? 'flex justify-center' : 'flex justify-start'}>
            {l.role === 'system' ? (
              <span className="text-xs text-[var(--color-text-muted)] bg-[var(--color-surface)] px-3 py-1 rounded-full">
                {l.text}
              </span>
            ) : (
              <div className="max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed bg-[var(--color-surface)] text-[var(--color-text)] rounded-tl-sm">
                <p>{l.text}</p>
                {l.meta && <p className="text-xs mt-1 font-mono opacity-60">{l.meta}</p>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
