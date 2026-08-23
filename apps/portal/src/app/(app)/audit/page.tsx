import Link from 'next/link'
import { ScrollText, Clock, User, Database, ChevronLeft, ChevronRight } from 'lucide-react'
import { serverFetch } from '@/lib/api/server'

interface AuditEvent {
  id: string
  actor: string | null
  action: string
  entity: string
  entityId: string | null
  diff: Record<string, unknown> | null
  createdAt: string
}

const PAGE_SIZE = 50

// Backend /audit nhận limit/offset (không phải page), xem apps/api/src/audit/audit.controller.ts —
// đã kiểm chứng bằng curl thật trước khi viết hàm này.
async function fetchAuditEvents(offset: number): Promise<{ data: AuditEvent[]; total: number }> {
  try {
    return await serverFetch<{ data: AuditEvent[]; total: number }>(`/audit?limit=${PAGE_SIZE}&offset=${offset}`)
  } catch {
    return { data: [], total: 0 }
  }
}

const ACTION_STYLE: Record<string, string> = {
  create: 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border-[oklch(88%_0.09_145)]',
  publish: 'bg-[oklch(96%_0.03_250)] text-[oklch(40%_0.16_250)] border-[oklch(88%_0.06_250)]',
  update: 'bg-[oklch(96%_0.08_85)] text-[oklch(42%_0.18_85)] border-[oklch(88%_0.12_85)]',
  delete: 'bg-[oklch(97%_0.04_27)] text-[oklch(42%_0.2_27)] border-[oklch(88%_0.08_27)]',
  review: 'bg-[oklch(96%_0.06_300)] text-[oklch(42%_0.16_300)] border-[oklch(88%_0.08_300)]',
}

function actionStyle(action: string) {
  const key = Object.keys(ACTION_STYLE).find((k) => action.toLowerCase().includes(k))
  return key ? ACTION_STYLE[key] : 'bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] border-[var(--color-border)]'
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>
}) {
  const params = await searchParams
  const page = Math.max(1, Number(params.page ?? 1) || 1)
  const offset = (page - 1) * PAGE_SIZE
  const { data: events, total } = await fetchAuditEvents(offset)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Audit Log</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Lịch sử mọi thay đổi trong hệ thống — {total} sự kiện, trang {page}/{totalPages}
        </p>
      </div>

      {events.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center rounded-xl border border-[var(--color-border)] bg-white">
          <div className="w-14 h-14 rounded-2xl bg-[oklch(96%_0.03_250)] flex items-center justify-center mb-4">
            <ScrollText className="w-7 h-7 text-[var(--color-accent)]" />
          </div>
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">
            Chưa có sự kiện nào
          </h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Audit log sẽ hiển thị sau khi có hoạt động trong hệ thống.
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--color-border)] bg-white overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Thời gian</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Actor</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Hành động</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Đối tượng</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.id} className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-overlay)] transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
                      <Clock className="w-3.5 h-3.5 shrink-0" />
                      <span className="text-xs tabular-nums">
                        {new Date(ev.createdAt).toLocaleString('vi-VN')}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-[var(--color-text-muted)] shrink-0" />
                      <span className="text-xs text-[var(--color-text)]">{ev.actor ?? 'system'}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold border ${actionStyle(ev.action)}`}>
                      {ev.action}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <Database className="w-3.5 h-3.5 text-[var(--color-text-muted)] shrink-0" />
                      <span className="text-xs text-[var(--color-text)]">{ev.entity}</span>
                      {ev.entityId && (
                        <span className="text-[10px] text-[var(--color-text-muted)] font-mono">
                          #{ev.entityId.slice(0, 8)}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>

          {/* Phân trang */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
              <Link
                href={`/audit?page=${Math.max(1, page - 1)}`}
                aria-disabled={page <= 1}
                className={`inline-flex items-center gap-1 text-xs font-medium ${
                  page <= 1
                    ? 'pointer-events-none text-[var(--color-text-muted)] opacity-50'
                    : 'text-[var(--color-text)] hover:text-[var(--color-accent)]'
                }`}
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                Trang trước
              </Link>
              <span className="text-xs text-[var(--color-text-muted)]">
                Trang {page} / {totalPages}
              </span>
              <Link
                href={`/audit?page=${Math.min(totalPages, page + 1)}`}
                aria-disabled={page >= totalPages}
                className={`inline-flex items-center gap-1 text-xs font-medium ${
                  page >= totalPages
                    ? 'pointer-events-none text-[var(--color-text-muted)] opacity-50'
                    : 'text-[var(--color-text)] hover:text-[var(--color-accent)]'
                }`}
              >
                Trang sau
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
