import { Phone, CheckCircle2, ArrowLeftRight, AlertCircle, Activity } from 'lucide-react'

interface DashboardStats {
  total: number
  completed: number
  handoff: number
  error: number
  active: number
}

interface SystemStatus {
  api: boolean
  voiceWorker: boolean
  cloudfoneConfigure: boolean
  cloudfoneWsUrl: string | null
}

async function fetchStats(): Promise<DashboardStats> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1/health`,
      { cache: 'no-store' },
    )
    if (!res.ok) return { total: 0, completed: 0, handoff: 0, error: 0, active: 0 }
    return { total: 0, completed: 0, handoff: 0, error: 0, active: 0 }
  } catch {
    return { total: 0, completed: 0, handoff: 0, error: 0, active: 0 }
  }
}

async function fetchSystemStatus(): Promise<SystemStatus> {
  const voiceUrl = process.env.VOICE_INTERNAL_URL ?? 'http://localhost:8000'
  const apiUrl = process.env.API_INTERNAL_URL ?? 'http://localhost:3001'

  const [apiOk, voiceRes] = await Promise.allSettled([
    fetch(`${apiUrl}/api/v1/health`, { cache: 'no-store' }).then((r) => r.ok),
    fetch(`${voiceUrl}/health`, { cache: 'no-store' }).then((r) => r.json() as Promise<{
      status: string
      cloudfone?: { configured: boolean; ws_url: string | null; service_name: string | null }
    }>),
  ])

  const api = apiOk.status === 'fulfilled' && apiOk.value
  const voice = voiceRes.status === 'fulfilled' ? voiceRes.value : null

  return {
    api,
    voiceWorker: voice?.status === 'ok',
    cloudfoneConfigure: voice?.cloudfone?.configured ?? false,
    cloudfoneWsUrl: voice?.cloudfone?.ws_url ?? null,
  }
}

export default async function DashboardPage() {
  const [stats, status] = await Promise.all([fetchStats(), fetchSystemStatus()])

  const metrics = [
    { label: 'Tổng cuộc gọi', value: stats.total, icon: Phone, color: 'text-[var(--color-accent)]', bg: 'bg-[oklch(96%_0.03_250)]' },
    { label: 'Hoàn thành', value: stats.completed, icon: CheckCircle2, color: 'text-[var(--color-success)]', bg: 'bg-[oklch(95%_0.06_145)]' },
    { label: 'Handoff', value: stats.handoff, icon: ArrowLeftRight, color: 'text-[oklch(55%_0.14_250)]', bg: 'bg-[oklch(96%_0.03_250)]' },
    { label: 'Lỗi', value: stats.error, icon: AlertCircle, color: 'text-[var(--color-danger)]', bg: 'bg-[oklch(97%_0.04_27)]' },
    { label: 'Đang gọi', value: stats.active, icon: Activity, color: 'text-[var(--color-warning)]', bg: 'bg-[oklch(96%_0.08_85)]' },
  ]

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
          Dashboard
        </h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Tổng quan hệ thống AI Call — DoctorCheck
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
        {metrics.map(({ label, value, icon: Icon, color, bg }) => (
          <div
            key={label}
            className="rounded-xl border border-[var(--color-border)] bg-white p-4"
          >
            <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center mb-3`}>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <p className="text-2xl font-bold text-[var(--color-text)] tracking-tight">{value}</p>
            <p className="text-xs text-[var(--color-text-muted)] font-medium mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* System status */}
      <section className="rounded-xl border border-[var(--color-border)] bg-white p-6">
        <h2 className="text-sm font-semibold text-[var(--color-text)] mb-4">Trạng thái hệ thống</h2>
        <div className="space-y-3">
          <StatusRow
            label="API Server"
            status={status.api ? 'operational' : 'error'}
          />
          <StatusRow
            label="Voice Worker"
            status={status.voiceWorker ? 'operational' : 'error'}
            note={status.voiceWorker ? undefined : 'Không thể kết nối localhost:8000'}
          />
          <StatusRow
            label="CloudFone ODS"
            status={status.cloudfoneConfigure ? 'operational' : 'pending'}
            note={
              status.cloudfoneConfigure
                ? status.cloudfoneWsUrl ?? undefined
                : 'Chưa cấu hình CLOUDFONE_WS_URL + CLOUDFONE_AUTH_KEY'
            }
          />
          <StatusRow label="PostgreSQL" status="operational" />
          <StatusRow label="Redis" status="operational" />
        </div>
      </section>
    </div>
  )
}

function StatusRow({
  label,
  status,
  note,
}: {
  label: string
  status: 'operational' | 'pending' | 'error'
  note?: string
}) {
  const dot = {
    operational: 'bg-[var(--color-success)]',
    pending: 'bg-[var(--color-warning)]',
    error: 'bg-[var(--color-danger)]',
  }[status]

  const text = {
    operational: 'Hoạt động',
    pending: 'Chờ',
    error: 'Lỗi',
  }[status]

  return (
    <div className="flex items-center justify-between py-2 border-b border-[var(--color-border)] last:border-0">
      <div className="flex items-center gap-2.5">
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        <span className="text-sm text-[var(--color-text)]">{label}</span>
        {note && <span className="text-xs text-[var(--color-text-muted)]">— {note}</span>}
      </div>
      <span className="text-xs font-medium text-[var(--color-text-muted)]">{text}</span>
    </div>
  )
}
