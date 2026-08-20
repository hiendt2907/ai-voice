import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { serverFetch } from '@/lib/api/server'
import { QaScoreForm } from './QaScoreForm'

interface CallSession {
  id: string
  sessionId: string
  campaignId: string | null
  direction: 'inbound' | 'outbound'
  callerNumberMasked: string | null
  status: 'active' | 'completed' | 'handoff' | 'error'
  transcript: Array<{ role?: string; text?: string; stepId?: string; ts?: string }> | null
  slots: Record<string, string> | null
  finalStepId: string | null
  traceId: string | null
  durationSeconds: number | null
  startedAt: string | null
  endedAt: string | null
  createdAt: string
}

import { TurnTrace, type TurnTraceData } from './TurnTrace'

interface CallTurn {
  id: string
  seq: number
  role: 'agent' | 'caller' | 'system'
  stepId: string | null
  intent: string | null
  text: string
  latencyMs: number | null
  /** Glassbox decision record, present on caller turns — see TurnTrace.tsx. */
  metadata: TurnTraceData | null
  createdAt: string
}

interface CallRecording {
  id: string
  storageKey: string
  format: string
  durationSeconds: number
}

interface QaScore {
  id: string
  score: number
  notes: string | null
  scoredBy: string
  createdAt: string
}

async function fetchSession(id: string): Promise<CallSession | null> {
  try {
    return await serverFetch<CallSession>(`/calls/${id}`)
  } catch {
    return null
  }
}

async function fetchTurns(id: string): Promise<CallTurn[]> {
  try {
    return await serverFetch<CallTurn[]>(`/calls/${id}/turns`)
  } catch {
    return []
  }
}

async function fetchRecording(id: string): Promise<CallRecording | null> {
  try {
    return await serverFetch<CallRecording | null>(`/calls/${id}/recording`)
  } catch {
    return null
  }
}

async function fetchQaScores(id: string): Promise<QaScore[]> {
  try {
    return await serverFetch<QaScore[]>(`/calls/${id}/qa-scores`)
  } catch {
    return []
  }
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Đang gọi',
  completed: 'Hoàn thành',
  handoff: 'Handoff',
  error: 'Lỗi',
}
const STATUS_COLOR: Record<string, string> = {
  active: 'text-[var(--color-warning)] bg-[oklch(96%_0.08_85)] border-[oklch(88%_0.12_85)]',
  completed: 'text-[oklch(38%_0.18_145)] bg-[oklch(95%_0.06_145)] border-[oklch(88%_0.09_145)]',
  handoff: 'text-[oklch(40%_0.16_250)] bg-[oklch(96%_0.03_250)] border-[oklch(88%_0.06_250)]',
  error: 'text-[var(--color-danger)] bg-[oklch(97%_0.04_27)] border-[oklch(88%_0.08_27)]',
}

function fmt(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

export default async function CallDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const [session, turns, recording, qaScores] = await Promise.all([
    fetchSession(id),
    fetchTurns(id),
    fetchRecording(id),
    fetchQaScores(id),
  ])

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Link
        href="/calls"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Cuộc gọi
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight mb-1">
            {session?.callerNumberMasked ?? 'Cuộc gọi ẩn danh'}
          </h1>
          <p className="text-xs font-mono text-[var(--color-text-muted)]">{id}</p>
        </div>
        {session && (
          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${STATUS_COLOR[session.status]}`}>
            {STATUS_LABELS[session.status]}
          </span>
        )}
      </div>

      {session && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <MetaCard label="Hướng" value={session.direction === 'inbound' ? 'Inbound' : 'Outbound'} />
          <MetaCard label="Thời lượng" value={session.durationSeconds != null ? fmt(session.durationSeconds) : '—'} />
          <MetaCard label="Bước cuối" value={session.finalStepId ?? '—'} mono />
        </div>
      )}

      {/* Recording */}
      {session?.traceId && (
        <section className="rounded-xl border border-[var(--color-border)] bg-white p-6 mb-6">
          <h2 className="text-sm font-semibold text-[var(--color-text)] mb-2">Trace</h2>
          <p className="text-xs text-[var(--color-text-muted)] mb-2">
            Một trace id duy nhất xuyên suốt cuộc gọi: softphone → voice worker → API.
          </p>
          <div className="flex items-center gap-3">
            <code className="rounded bg-[var(--color-surface-overlay)] px-2 py-1 text-xs">
              {session.traceId}
            </code>
            <a
              href={`${process.env.NEXT_PUBLIC_GRAFANA_URL ?? ''}/explore?left=${encodeURIComponent(
                JSON.stringify({
                  datasource: 'tempo',
                  queries: [{ query: session.traceId, queryType: 'traceql' }],
                }),
              )}`}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-[var(--color-accent)] hover:underline"
            >
              Mở trong Grafana/Tempo →
            </a>
          </div>
        </section>
      )}

      <section className="rounded-xl border border-[var(--color-border)] bg-white p-6 mb-6">
        <h2 className="text-sm font-semibold text-[var(--color-text)] mb-3">Ghi âm</h2>
        {recording ? (
          <div className="space-y-3">
            <audio
              controls
              src={`/api/stream/recording/${id}`}
              className="w-full h-10 rounded-lg"
              preload="metadata"
            />
            <div className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-surface-overlay)] text-xs text-[var(--color-text-muted)]">
              <span className="font-mono truncate">{recording.storageKey}</span>
              <span className="ml-auto shrink-0">{fmt(recording.durationSeconds)} · {recording.format.toUpperCase()}</span>
            </div>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">Chưa có bản ghi âm cho cuộc gọi này.</p>
        )}
      </section>

      {/* Transcript / Turns */}
      <section className="rounded-xl border border-[var(--color-border)] bg-white p-6 mb-6">
        <h2 className="text-sm font-semibold text-[var(--color-text)] mb-4">Transcript</h2>
        {turns.length > 0 ? (
          <div className="space-y-3">
            {turns.map((turn) => {
              const isAgent = turn.role === 'agent' || turn.role === 'system'
              return (
                <div key={turn.id} className={`flex gap-3 ${isAgent ? '' : 'flex-row-reverse'}`}>
                  <div className={`w-6 h-6 rounded-full shrink-0 flex items-center justify-center text-[10px] font-bold ${isAgent ? 'bg-[oklch(96%_0.03_250)] text-[var(--color-accent)]' : 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)]'}`}>
                    {isAgent ? 'AI' : 'U'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${isAgent ? 'bg-[var(--color-surface-overlay)] text-[var(--color-text)]' : 'bg-[oklch(55%_0.2_250)] text-white'} ${isAgent ? '' : 'ml-auto'}`}>
                      {turn.text || '(trống)'}
                    </div>
                    {(turn.intent || turn.latencyMs) && (
                      <div className={`mt-0.5 flex gap-2 text-[10px] text-[var(--color-text-muted)] ${isAgent ? '' : 'justify-end'}`}>
                        {turn.intent && <span>intent: {turn.intent}</span>}
                        {turn.latencyMs && <span>{turn.latencyMs}ms</span>}
                      </div>
                    )}
                    {turn.metadata && (
                      <details className="mt-2">
                        <summary className="cursor-pointer text-[11px] text-[var(--color-accent)]">
                          Vì sao AI trả lời như vậy?
                        </summary>
                        <div className="mt-2">
                          <TurnTrace data={turn.metadata} />
                        </div>
                      </details>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ) : session?.transcript && session.transcript.length > 0 ? (
          <div className="space-y-3">
            {session.transcript.map((turn, i) => {
              const isAgent = turn.role === 'agent' || turn.role === 'system'
              return (
                <div key={i} className={`flex gap-3 ${isAgent ? '' : 'flex-row-reverse'}`}>
                  <div className={`w-6 h-6 rounded-full shrink-0 flex items-center justify-center text-[10px] font-bold ${isAgent ? 'bg-[oklch(96%_0.03_250)] text-[var(--color-accent)]' : 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)]'}`}>
                    {isAgent ? 'AI' : 'U'}
                  </div>
                  <div className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${isAgent ? 'bg-[var(--color-surface-overlay)] text-[var(--color-text)]' : 'bg-[oklch(55%_0.2_250)] text-white'}`}>
                    {turn.text ?? JSON.stringify(turn)}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            {session ? 'Không có transcript.' : 'Không tìm thấy cuộc gọi này.'}
          </p>
        )}
      </section>

      {/* Slots */}
      {session?.slots && Object.keys(session.slots).length > 0 && (
        <section className="rounded-xl border border-[var(--color-border)] bg-white p-6 mb-6">
          <h2 className="text-sm font-semibold text-[var(--color-text)] mb-4">Slots</h2>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(session.slots).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between p-3 rounded-lg bg-[var(--color-surface-overlay)]">
                <span className="text-xs font-mono text-[var(--color-text-muted)]">{k}</span>
                <span className="text-xs font-semibold text-[var(--color-text)]">{v}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* QA */}
      <QaScoreForm callId={id} existingScores={qaScores} />
    </div>
  )
}

function MetaCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
      <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-base font-semibold text-[var(--color-text)] ${mono ? 'font-mono' : ''}`}>{value}</p>
    </div>
  )
}
