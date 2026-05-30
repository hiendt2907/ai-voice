import Link from 'next/link'
import { Star, CheckCircle2, ArrowRight, Clock } from 'lucide-react'
import { serverFetch } from '@/lib/api/server'

interface CallSession {
  id: string
  sessionId: string
  direction: 'inbound' | 'outbound'
  callerNumberMasked: string | null
  status: string
  durationSeconds: number | null
  createdAt: string
}

type TabId = 'pending' | 'reviewed' | 'all'

async function fetchQaQueue(tab: TabId): Promise<CallSession[]> {
  try {
    if (tab === 'pending') return await serverFetch<CallSession[]>('/calls/qa-queue')
    if (tab === 'reviewed') return await serverFetch<CallSession[]>('/calls/qa-queue?reviewed=true')
    const resp = await serverFetch<{ data: CallSession[]; total: number }>('/calls?limit=50')
    return resp.data
  } catch {
    return []
  }
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'pending', label: 'Chờ chấm' },
  { id: 'reviewed', label: 'Đã chấm' },
  { id: 'all', label: 'Tất cả' },
]

export default async function QaPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>
}) {
  const params = await searchParams
  const tab = (params.tab ?? 'pending') as TabId
  const queue = await fetchQaQueue(tab)

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
          QA Review Queue
        </h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          {tab === 'pending' ? `${queue.length} cuộc gọi chờ đánh giá` : `${queue.length} cuộc gọi`}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-lg bg-[var(--color-surface-overlay)] w-fit">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={`/qa?tab=${t.id}`}
            className={[
              'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
              t.id === tab
                ? 'bg-white text-[var(--color-text)] shadow-sm'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]',
            ].join(' ')}
          >
            {t.label}
          </Link>
        ))}
      </div>

      {queue.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[oklch(96%_0.02_145)] flex items-center justify-center mb-4">
            {tab === 'pending' ? (
              <Clock className="w-7 h-7 text-[var(--color-warning)]" />
            ) : (
              <CheckCircle2 className="w-7 h-7 text-[var(--color-success)]" />
            )}
          </div>
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">
            {tab === 'pending' ? 'Không có cuộc gọi chờ review' : 'Chưa có dữ liệu'}
          </h3>
          <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
            {tab === 'pending'
              ? 'Các cuộc gọi hoàn thành chưa được chấm điểm QA sẽ xuất hiện ở đây. QA review giúp cải thiện chất lượng AI.'
              : 'Chưa có cuộc gọi nào trong danh mục này.'}
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
