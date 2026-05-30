'use client'

import { useEffect, useState } from 'react'
import { Activity, PhoneOff } from 'lucide-react'

interface ActiveCall {
  sessionId: string
  callerNumberMasked: string | null
  campaignId: string | null
  finalStepId: string | null
  durationSeconds: number
  startedAt: string | null
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m${s.toString().padStart(2, '0')}s`
}

export function LiveCallMonitor() {
  const [calls, setCalls] = useState<ActiveCall[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchActive() {
      try {
        const res = await fetch('/api/v1/calls/active')
        if (res.ok) setCalls((await res.json()) as ActiveCall[])
      } finally {
        setLoading(false)
      }
    }

    void fetchActive()
    const interval = setInterval(() => void fetchActive(), 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return null

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white p-5 mb-4">
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center gap-1.5">
          {calls.length > 0 && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-success)] opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-success)]" />
            </span>
          )}
          <Activity className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
        </div>
        <h2 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">
          Cuộc gọi đang diễn ra
        </h2>
        {calls.length > 0 && (
          <span className="ml-auto text-xs font-semibold text-[var(--color-success)] bg-[oklch(95%_0.06_145)] px-2 py-0.5 rounded-full">
            {calls.length} active
          </span>
        )}
      </div>

      {calls.length === 0 ? (
        <div className="flex items-center gap-2 py-3 text-[var(--color-text-muted)]">
          <PhoneOff className="w-4 h-4" />
          <p className="text-xs">Không có cuộc gọi đang diễn ra</p>
        </div>
      ) : (
        <div className="space-y-2">
          {calls.map((call) => (
            <div
              key={call.sessionId}
              className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-surface-overlay)] text-xs"
            >
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-success)] opacity-60" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-success)]" />
              </span>
              <span className="text-[var(--color-text-muted)] font-mono min-w-[90px]">
                {call.callerNumberMasked ?? '—'}
              </span>
              <span className="text-[var(--color-text)] font-medium min-w-[100px] truncate">
                {call.campaignId ?? '—'}
              </span>
              <span className="text-[var(--color-text-muted)] font-mono min-w-[80px]">
                {call.finalStepId ?? 'greeting'}
              </span>
              <span className="ml-auto text-[var(--color-text-muted)] font-mono tabular-nums">
                {formatDuration(call.durationSeconds)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
