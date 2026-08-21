import Link from 'next/link'
import { Phone, PhoneIncoming, PhoneOutgoing, Clock, CheckCircle2, AlertCircle, ArrowLeftRight, X } from 'lucide-react'
import { serverFetch } from '@/lib/api/server'

type CallStatus = 'active' | 'completed' | 'handoff' | 'error'

interface CallSession {
  id: string
  sessionId: string
  campaignId: string | null
  direction: 'inbound' | 'outbound'
  callerNumberMasked: string | null
  status: CallStatus
  finalStepId: string | null
  durationSeconds: number | null
  createdAt: string
}

interface ListResponse {
  data: CallSession[]
  total: number
}

async function fetchCalls(page = 1, status?: string): Promise<ListResponse> {
  try {
    const params = new URLSearchParams({ page: String(page), limit: '20' })
    if (status) params.set('status', status)
    return await serverFetch<ListResponse>(`/calls?${params.toString()}`)
  } catch {
    return { data: [], total: 0 }
  }
}

const STATUS_META: Record<CallStatus, { label: string; color: string; icon: React.ComponentType<{ className?: string }> }> = {
  active: { label: 'Active', color: 'bg-[oklch(96%_0.08_85)] text-[oklch(42%_0.18_85)] border-[oklch(88%_0.12_85)]', icon: Clock },
  completed: { label: 'Completed', color: 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border-[oklch(88%_0.09_145)]', icon: CheckCircle2 },
  handoff: { label: 'Handoff', color: 'bg-[oklch(96%_0.03_250)] text-[oklch(42%_0.12_250)] border-[oklch(88%_0.06_250)]', icon: ArrowLeftRight },
  error: { label: 'Error', color: 'bg-[oklch(97%_0.04_27)] text-[oklch(42%_0.2_27)] border-[oklch(88%_0.08_27)]', icon: AlertCircle },
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Đang gọi',
  completed: 'Hoàn thành',
  handoff: 'Handoff',
  error: 'Lỗi',
}

export default async function CallsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; page?: string }>
}) {
  const params = await searchParams
  const status = params.status
  const page = Number(params.page ?? 1)
  const { data: calls, total } = await fetchCalls(page, status)

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
            Cuộc gọi
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            {total} cuộc gọi{status ? ` — đang lọc theo "${STATUS_LABELS[status] ?? status}"` : ' đã ghi nhận'}
          </p>
        </div>
      </div>

      {/* Active filter badge */}
      {status && (
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xs text-[var(--color-text-muted)]">Đang lọc:</span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-[oklch(96%_0.03_250)] text-[var(--color-accent)] border border-[oklch(88%_0.06_250)]">
            {STATUS_LABELS[status] ?? status}
            <Link href="/calls" className="hover:opacity-70 transition-opacity">
              <X className="w-3 h-3" />
            </Link>
          </span>
        </div>
      )}

      {calls.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[oklch(96%_0.02_250)] flex items-center justify-center mb-4">
            <Phone className="w-7 h-7 text-[var(--color-accent)]" />
          </div>
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">Chưa có cuộc gọi</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            {status ? `Không có cuộc gọi nào có trạng thái "${STATUS_LABELS[status] ?? status}".` : 'Cuộc gọi sẽ xuất hiện ở đây sau khi Voice Worker được kết nối.'}
          </p>
          {status && (
            <Link href="/calls" className="mt-4 text-sm text-[var(--color-accent)] hover:underline">
              Xem tất cả cuộc gọi
            </Link>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[oklch(97%_0.005_250)] border-b border-[var(--color-border)]">
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Hướng</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Số điện thoại</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Thời lượng</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Thời gian</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {calls.map((call) => {
                const meta = STATUS_META[call.status]
                const StatusIcon = meta.icon
                const DirIcon = call.direction === 'inbound' ? PhoneIncoming : PhoneOutgoing
                return (
                  <tr key={call.id} className="hover:bg-[oklch(98.5%_0.003_250)] transition-colors">
                    <td className="px-4 py-3.5">
                      <span className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
                        <DirIcon className="w-3.5 h-3.5" />
                        <span className="capitalize">{call.direction}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs text-[var(--color-text)]">
                      {call.callerNumberMasked ?? '—'}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${meta.color}`}>
                        <StatusIcon className="w-2.5 h-2.5" />
                        {meta.label}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-[var(--color-text-muted)] text-xs">
                      {call.durationSeconds != null ? `${call.durationSeconds}s` : '—'}
                    </td>
                    <td className="px-4 py-3.5 text-[var(--color-text-muted)] text-xs">
                      {new Date(call.createdAt).toLocaleString('vi-VN')}
                    </td>
                    <td className="px-4 py-3.5">
                      <Link
                        href={`/calls/${call.id}`}
                        className="text-xs font-medium text-[var(--color-accent)] hover:underline"
                      >
                        Chi tiết →
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  )
}
