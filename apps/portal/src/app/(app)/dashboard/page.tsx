import Link from 'next/link'
import { Phone, CheckCircle2, ArrowLeftRight, AlertCircle, Activity, Server, Database, Cpu, Radio, Plus, Star, Bot, AlertTriangle } from 'lucide-react'
import { serverFetch } from '@/lib/api/server'
import { LiveCallMonitor } from './LiveCallMonitor'

interface OverviewResponse {
  calls: { total: number; completed: number; handoff: number; error: number; active: number }
  period: string
  containmentRate: number
  avgQaScore: number
}

interface DepsHealth {
  postgres: 'ok' | 'error'
  redis: 'ok' | 'error'
  timestamp: string
}

interface VoiceHealth {
  status: 'ok' | 'error'
  cloudfone?: { configured: boolean }
}

// Kết quả gọi overview: phân biệt rõ "lấy thành công" (kể cả toàn số 0 khi thật sự chưa có dữ
// liệu) với "gọi API thất bại" — không được lẫn hai trường hợp này thành cùng một giao diện.
type OverviewResult =
  | { ok: true; data: OverviewResponse }
  | { ok: false }

async function fetchOverview(): Promise<OverviewResult> {
  try {
    const data = await serverFetch<OverviewResponse>('/analytics/overview')
    return { ok: true, data }
  } catch {
    return { ok: false }
  }
}

async function fetchDepsHealth(): Promise<DepsHealth | null> {
  try {
    return await serverFetch<DepsHealth>('/health/deps')
  } catch {
    return null
  }
}

async function fetchVoiceHealth(): Promise<VoiceHealth | null> {
  try {
    const voiceUrl = process.env.VOICE_WORKER_URL ?? 'http://localhost:8000'
    const res = await fetch(`${voiceUrl}/health`, { next: { revalidate: 10 } })
    if (!res.ok) return null
    return await res.json() as VoiceHealth
  } catch {
    return null
  }
}

// Cũng phân biệt "chờ chấm QA = 0" thật với "không lấy được danh sách QA queue".
type QaPendingResult = { ok: true; count: number } | { ok: false }

async function fetchQaPendingCount(): Promise<QaPendingResult> {
  try {
    const data = await serverFetch<unknown[]>('/calls/qa-queue')
    return { ok: true, count: Array.isArray(data) ? data.length : 0 }
  } catch {
    return { ok: false }
  }
}

export default async function DashboardPage() {
  const [overviewResult, deps, voice, qaPendingResult] = await Promise.all([
    fetchOverview(),
    fetchDepsHealth(),
    fetchVoiceHealth(),
    fetchQaPendingCount(),
  ])

  // deps là tín hiệu thật duy nhất cho biết API có phản hồi hay không — fetchDepsHealth() trả
  // null khi request lỗi (network fail, non-2xx, JSON hỏng). Không được hardcode true nữa.
  const apiOk = deps !== null
  const overviewFailed = !overviewResult.ok
  const calls = overviewResult.ok
    ? overviewResult.data.calls
    : { total: 0, completed: 0, handoff: 0, error: 0, active: 0 }
  const containmentRate = overviewResult.ok ? overviewResult.data.containmentRate : 0
  const avgQaScore = overviewResult.ok ? overviewResult.data.avgQaScore : 0

  const kpiCards = [
    { label: 'Tổng cuộc gọi', value: calls.total, icon: Phone, color: 'text-[var(--color-accent)]', bg: 'bg-[oklch(96%_0.03_250)]', href: '/calls' },
    { label: 'Hoàn thành', value: calls.completed, icon: CheckCircle2, color: 'text-[var(--color-success)]', bg: 'bg-[oklch(95%_0.06_145)]', href: '/calls?status=completed' },
    { label: 'Handoff', value: calls.handoff, icon: ArrowLeftRight, color: 'text-[oklch(55%_0.14_250)]', bg: 'bg-[oklch(96%_0.03_250)]', href: '/calls?status=handoff' },
    { label: 'Lỗi', value: calls.error, icon: AlertCircle, color: 'text-[var(--color-danger)]', bg: 'bg-[oklch(97%_0.04_27)]', href: '/calls?status=error' },
    { label: 'Đang gọi', value: calls.active, icon: Activity, color: 'text-[var(--color-warning)]', bg: 'bg-[oklch(96%_0.08_85)]', href: '/calls?status=active' },
  ]

  const postgresOk = deps?.postgres === 'ok'
  const redisOk = deps?.redis === 'ok'
  const voiceOk = voice?.status === 'ok'

  const healthItems = [
    { label: 'API Server', ok: apiOk, icon: Server, detail: ':3001' },
    { label: 'Voice Worker', ok: voiceOk, icon: Radio, detail: ':8000' },
    { label: 'PostgreSQL', ok: postgresOk, icon: Database, detail: deps ? 'connected' : 'unreachable' },
    { label: 'Redis', ok: redisOk, icon: Cpu, detail: deps ? 'connected' : 'unreachable' },
  ]

  // Banner "hệ thống sẵn sàng, chưa có cuộc gọi" chỉ hợp lệ khi ta THẬT SỰ biết total = 0.
  // Khi gọi overview lỗi, calls.total cũng là 0 nhưng đó là dữ liệu giả — không được hiện banner này.
  const isFirstRun = !overviewFailed && calls.total === 0

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Dashboard</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Tổng quan hệ thống AI Call — DoctorCheck
        </p>
      </div>

      {/* Banner cảnh báo khi không lấy được dữ liệu overview — không được lẫn với "chưa có cuộc gọi" */}
      {overviewFailed && (
        <div className="mb-6 rounded-xl border border-[oklch(88%_0.08_27)] bg-[oklch(97%_0.04_27)] p-5">
          <div className="flex items-start gap-4">
            <div className="w-9 h-9 rounded-lg bg-[oklch(93%_0.08_27)] flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5 text-[var(--color-danger)]" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-[var(--color-text)] mb-1">Không lấy được số liệu tổng quan</h3>
              <p className="text-xs text-[var(--color-text-muted)]">
                API không phản hồi truy vấn <code>/analytics/overview</code>. Các số liệu bên dưới đang hiển thị 0 vì
                lỗi kết nối, không phải vì hệ thống chưa có cuộc gọi nào. Kiểm tra API Server ở mục System Health bên dưới.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* First-run banner */}
      {isFirstRun && (
        <div className="mb-6 rounded-xl border border-[oklch(88%_0.06_250)] bg-[oklch(97%_0.02_250)] p-5">
          <div className="flex items-start gap-4">
            <div className="w-9 h-9 rounded-lg bg-[oklch(93%_0.06_250)] flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-[var(--color-accent)]" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-[var(--color-text)] mb-1">Hệ thống sẵn sàng — chưa có cuộc gọi nào</h3>
              <p className="text-xs text-[var(--color-text-muted)] mb-3">
                Tạo campaign, cài đặt voice script, rồi chạy thử Simulator để kiểm tra luồng AI trước khi kết nối CloudFone thật.
              </p>
              <div className="flex flex-wrap gap-2">
                <Link href="/scripts/new" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--color-accent)] text-white text-xs font-medium hover:bg-[var(--color-accent-hover)] transition-colors">
                  <Plus className="w-3.5 h-3.5" />
                  Tạo Campaign
                </Link>
                <Link href="/simulator" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-[var(--color-border)] text-[var(--color-text)] text-xs font-medium hover:bg-[var(--color-surface-overlay)] transition-colors">
                  <Cpu className="w-3.5 h-3.5" />
                  Chạy Simulator
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Live call monitor */}
      <LiveCallMonitor />

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
        {kpiCards.map(({ label, value, icon: Icon, color, bg, href }) => (
          <Link
            key={label}
            href={href}
            className="group rounded-xl border border-[var(--color-border)] bg-white p-4 hover:shadow-md hover:border-[var(--color-accent)] transition-all duration-[var(--duration-fast)]"
          >
            <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center mb-3`}>
              {label === 'Đang gọi' && value > 0
                ? <span className="relative flex h-4 w-4">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-warning)] opacity-50" />
                    <Icon className={`relative w-4 h-4 ${color}`} />
                  </span>
                : <Icon className={`w-4 h-4 ${color}`} />
              }
            </div>
            <p className="text-2xl font-bold text-[var(--color-text)] tracking-tight">{value}</p>
            <p className="text-xs text-[var(--color-text-muted)] font-medium mt-0.5">{label}</p>
          </Link>
        ))}
      </div>

      {/* Secondary row: KPIs + System health */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {/* Containment */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">Containment Rate</p>
          <p className="text-2xl font-bold text-[var(--color-text)]">
            {(containmentRate * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">Cuộc gọi AI xử lý hoàn toàn</p>
        </div>

        {/* QA Score */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">Avg QA Score</p>
          <p className="text-2xl font-bold text-[var(--color-text)]">
            {avgQaScore.toFixed(1)}{' '}
            <span className="text-sm font-normal text-[var(--color-text-muted)]">/ 5</span>
          </p>
          {qaPendingResult.ok && qaPendingResult.count > 0 && (
            <Link href="/qa" className="text-xs text-[var(--color-warning)] hover:underline mt-1 block">
              {qaPendingResult.count} cuộc gọi chờ chấm →
            </Link>
          )}
          {!qaPendingResult.ok && (
            <p className="text-xs text-[var(--color-danger)] mt-1">Không lấy được QA queue</p>
          )}
        </div>

        {/* Quick actions */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-3">Nhanh</p>
          <div className="space-y-1.5">
            <Link href="/scripts/new" className="flex items-center gap-2 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors">
              <Plus className="w-3.5 h-3.5" />Tạo Campaign
            </Link>
            <Link href="/simulator" className="flex items-center gap-2 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors">
              <Cpu className="w-3.5 h-3.5" />Chạy Simulator
            </Link>
            <Link href="/qa" className="flex items-center gap-2 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors">
              <Star className="w-3.5 h-3.5" />QA Queue
            </Link>
          </div>
        </div>
      </div>

      {/* System Health */}
      <div className="rounded-xl border border-[var(--color-border)] bg-white p-5">
        <h2 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">System Health</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {healthItems.map(({ label, ok, icon: Icon, detail }) => (
            <div key={label} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-surface-overlay)]">
              <div className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 ${ok ? 'bg-[oklch(95%_0.06_145)]' : 'bg-[oklch(97%_0.04_27)]'}`}>
                <Icon className={`w-3.5 h-3.5 ${ok ? 'text-[var(--color-success)]' : 'text-[var(--color-danger)]'}`} />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-[var(--color-text)] leading-none">{label}</p>
                <div className="flex items-center gap-1 mt-1">
                  <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-[var(--color-success)]' : 'bg-[var(--color-danger)]'}`} />
                  <span className="text-[10px] text-[var(--color-text-muted)] truncate">{ok ? detail : 'offline'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
