import Link from 'next/link'
import { Star, CheckCircle2, ArrowRight } from 'lucide-react'

interface CallSession {
  id: string
  sessionId: string
  direction: 'inbound' | 'outbound'
  callerNumberMasked: string | null
  status: string
  durationSeconds: number | null
  createdAt: string
}

async function fetchQaQueue(): Promise<CallSession[]> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1/calls/qa-queue`,
      { cache: 'no-store' },
    )
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export default async function QaPage() {
  const queue = await fetchQaQueue()

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
          QA Review Queue
        </h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          {queue.length} cuộc gọi chờ đánh giá
        </p>
      </div>

      {queue.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[oklch(96%_0.02_145)] flex items-center justify-center mb-4">
            <CheckCircle2 className="w-7 h-7 text-[var(--color-success)]" />
          </div>
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">
            Không có cuộc gọi chờ review
          </h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Tất cả cuộc gọi đã được đánh giá QA.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {queue.map((call) => (
            <Link
              key={call.id}
              href={`/calls/${call.id}`}
              className="group flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-white hover:border-[var(--color-accent)] hover:shadow-sm transition-all duration-[var(--duration-fast)]"
            >
              <div className="flex items-center gap-4">
                <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_85)] flex items-center justify-center">
                  <Star className="w-4 h-4 text-[var(--color-warning)]" />
                </div>
                <div>
                  <p className="text-sm font-medium text-[var(--color-text)]">
                    {call.callerNumberMasked ?? call.sessionId.slice(0, 8) + '…'}
                  </p>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    {call.direction === 'inbound' ? 'Inbound' : 'Outbound'} ·{' '}
                    {call.durationSeconds != null ? `${call.durationSeconds}s` : '—'} ·{' '}
                    {new Date(call.createdAt).toLocaleString('vi-VN')}
                  </p>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-accent)] transition-colors" />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
