import { Lightbulb, CheckCircle2, XCircle, Clock, ArrowRight } from 'lucide-react'
import Link from 'next/link'

type ProposalStatus = 'pending' | 'approved' | 'rejected'
type ProposalType = 'new_intent_example' | 'edit_variant' | 'add_reprompt' | 'slot_correction'

interface Proposal {
  id: string
  type: ProposalType
  status: ProposalStatus
  callSessionId: string | null
  payload: Record<string, unknown>
  reviewedBy: string | null
  reviewedAt: string | null
  createdAt: string
}

async function fetchProposals(status = 'pending'): Promise<Proposal[]> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1/learning/proposals?status=${status}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

const TYPE_LABELS: Record<ProposalType, string> = {
  new_intent_example: 'New Intent Example',
  edit_variant: 'Edit Variant',
  add_reprompt: 'Add Reprompt',
  slot_correction: 'Slot Correction',
}

const STATUS_META: Record<ProposalStatus, { label: string; color: string; icon: React.ComponentType<{ className?: string }> }> = {
  pending: { label: 'Chờ duyệt', color: 'bg-[oklch(96%_0.08_85)] text-[oklch(42%_0.18_85)] border-[oklch(88%_0.12_85)]', icon: Clock },
  approved: { label: 'Đã duyệt', color: 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border-[oklch(88%_0.09_145)]', icon: CheckCircle2 },
  rejected: { label: 'Từ chối', color: 'bg-[oklch(97%_0.04_27)] text-[oklch(42%_0.2_27)] border-[oklch(88%_0.08_27)]', icon: XCircle },
}

export default async function LearningPage() {
  const proposals = await fetchProposals('pending')

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
          Learning Queue
        </h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          HITL review — {proposals.length} đề xuất chờ duyệt
        </p>
      </div>

      {/* Tabs (static for now) */}
      <div className="flex gap-1 mb-6 p-1 rounded-lg bg-[var(--color-surface-overlay)] w-fit">
        {(['pending', 'approved', 'rejected'] as ProposalStatus[]).map((s) => (
          <span
            key={s}
            className={[
              'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
              s === 'pending'
                ? 'bg-white text-[var(--color-text)] shadow-sm'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]',
            ].join(' ')}
          >
            {STATUS_META[s].label}
          </span>
        ))}
      </div>

      {proposals.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[oklch(96%_0.02_145)] flex items-center justify-center mb-4">
            <CheckCircle2 className="w-7 h-7 text-[var(--color-success)]" />
          </div>
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">
            Không có đề xuất chờ duyệt
          </h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Hệ thống sẽ tự động tạo đề xuất dựa trên phân tích cuộc gọi.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {proposals.map((p) => {
            const meta = STATUS_META[p.status]
            const StatusIcon = meta.icon
            return (
              <div
                key={p.id}
                className="flex items-start gap-4 p-4 rounded-xl border border-[var(--color-border)] bg-white"
              >
                <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_250)] flex items-center justify-center shrink-0 mt-0.5">
                  <Lightbulb className="w-4 h-4 text-[var(--color-accent)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-[var(--color-text)]">
                      {TYPE_LABELS[p.type]}
                    </span>
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${meta.color}`}>
                      <StatusIcon className="w-2.5 h-2.5" />
                      {meta.label}
                    </span>
                  </div>
                  <pre className="text-xs text-[var(--color-text-muted)] bg-[var(--color-surface-overlay)] rounded p-2 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(p.payload, null, 2)}
                  </pre>
                  <div className="flex items-center gap-4 mt-2 text-xs text-[var(--color-text-muted)]">
                    <span>{new Date(p.createdAt).toLocaleString('vi-VN')}</span>
                    {p.callSessionId && (
                      <Link href={`/calls/${p.callSessionId}`} className="text-[var(--color-accent)] hover:underline flex items-center gap-0.5">
                        Xem cuộc gọi <ArrowRight className="w-3 h-3" />
                      </Link>
                    )}
                  </div>
                </div>
                {p.status === 'pending' && (
                  <div className="flex gap-2 shrink-0">
                    <button className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border border-[oklch(88%_0.09_145)] hover:opacity-80 transition-opacity">
                      Duyệt
                    </button>
                    <button className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[oklch(97%_0.04_27)] text-[oklch(42%_0.2_27)] border border-[oklch(88%_0.08_27)] hover:opacity-80 transition-opacity">
                      Từ chối
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
