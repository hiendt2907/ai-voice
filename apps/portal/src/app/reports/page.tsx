import { BarChart2, TrendingUp, Clock, Star } from 'lucide-react'

export default function ReportsPage() {
  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Báo cáo</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">Analytics — Sprint 7</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <PlaceholderCard
          icon={BarChart2}
          title="Cuộc gọi theo ngày"
          desc="Biểu đồ số cuộc gọi inbound/outbound theo ngày trong 30 ngày gần nhất."
        />
        <PlaceholderCard
          icon={TrendingUp}
          title="Intent phổ biến"
          desc="Top intents được nhận dạng — book_appointment, check_result, cancel, speak_to_staff."
        />
        <PlaceholderCard
          icon={Clock}
          title="Thời lượng trung bình"
          desc="Thời lượng cuộc gọi trung bình theo campaign và kết quả (completed/handoff/error)."
        />
        <PlaceholderCard
          icon={Star}
          title="Điểm QA trung bình"
          desc="Phân phối điểm QA theo tuần — phân tích xu hướng chất lượng cuộc gọi."
        />
      </div>

      <div className="mt-8 p-5 rounded-xl border border-dashed border-[var(--color-border)] text-center">
        <p className="text-sm text-[var(--color-text-muted)]">
          Analytics sẽ được implement đầy đủ trong Sprint 7.
          <br />
          Dữ liệu từ <code className="font-mono text-xs bg-[var(--color-surface-overlay)] px-1 rounded">call_sessions</code> và{' '}
          <code className="font-mono text-xs bg-[var(--color-surface-overlay)] px-1 rounded">qa_scores</code> tables.
        </p>
      </div>
    </div>
  )
}

function PlaceholderCard({
  icon: Icon,
  title,
  desc,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  desc: string
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-[var(--color-surface-overlay)] flex items-center justify-center">
          <Icon className="w-4 h-4 text-[var(--color-accent)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{title}</h3>
      </div>
      <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">{desc}</p>
      <div className="mt-4 h-24 rounded-lg bg-[var(--color-surface-overlay)] flex items-center justify-center">
        <span className="text-xs text-[var(--color-text-muted)]">Chart — Sprint 7</span>
      </div>
    </div>
  )
}
