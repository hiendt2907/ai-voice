import { ScrollText, Clock, User, Database } from 'lucide-react'
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

async function fetchAuditEvents(): Promise<AuditEvent[]> {
  try {
    const res = await serverFetch<{ data: AuditEvent[]; total: number }>('/audit?limit=50')
    return res.data
  } catch {
    return []
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

export default async function AuditPage() {
  const events = await fetchAuditEvents()

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Audit Log</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Lịch sử mọi thay đổi trong hệ thống — {events.length} sự kiện gần nhất
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
        </div>
      )}
    </div>
  )
}
