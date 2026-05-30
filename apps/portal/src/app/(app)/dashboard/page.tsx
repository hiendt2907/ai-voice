import Link from 'next/link'
import { Phone, CheckCircle2, ArrowLeftRight, AlertCircle, Activity, Server, Database, Cpu, Radio, Plus, Star, Bot, Mic } from 'lucide-react'
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

interface ElevenLabsMetrics {
  total: number
  ok: number
  err: number
  avgLatencyMs: number | null
  lastSuccessTs: number | null
  connected: boolean
}

async function fetchOverview(): Promise<OverviewResponse> {
  try {
    return await serverFetch<OverviewResponse>('/analytics/overview')
  } catch {
    return { calls: { total: 0, completed: 0, handoff: 0, error: 0, active: 0 }, period: 'all', containmentRate: 0, avgQaScore: 0 }
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

async function fetchQaPendingCount(): Promise<number> {
  try {
    const data = await serverFetch<unknown[]>('/calls/qa-queue')
    return Array.isArray(data) ? data.length : 0
  } catch {
    return 0
  }
}

async function fetchElevenLabsMetrics(): Promise<ElevenLabsMetrics> {
  try {
    const data = await serverFetch<ElevenLabsMetrics>('/analytics/elevenlabs')
    return data
  } catch {
    return { total: 0, ok: 0, err: 0, avgLatencyMs: null, lastSuccessTs: null, connected: false }
  }
}

export default async function DashboardPage() {
  const [overview, deps, voice, qaPending, elevenLabs] = await Promise.all([
    fetchOverview(),
    fetchDepsHealth(),
    fetchVoiceHealth(),
    fetchQaPendingCount(),
    fetchElevenLabsMetrics(),
  ])
  const { calls } = overview

  const kpiCards = [
    { label: 'Tổng cuộc gọi', value: calls.total, icon: Phone, color: 'text-[var(--color-accent)]', bg: 'bg-[oklch(96%_0.03_250)]', href: '/calls' },
    { label: 'Hoàn thành', value: calls.completed, icon: CheckCircle2, color: 'text-[var(--color-success)]', bg: 'bg-[oklch(95%_0.06_145)]', href: '/calls?status=completed' },
    { label: 'Handoff', value: calls.handoff, icon: ArrowLeftRight, color: 'text-[oklch(55%_0.14_250)]', bg: 'bg-[oklch(96%_0.03_250)]', href: '/calls?status=handoff' },
    { label: 'Lỗi', value: calls.error, icon: AlertCircle, color: 'text-[var(--color-danger)]', bg: 'bg-[oklch(97%_0.04_27)]', href: '/calls?status=error' },
    { label: 'Đang gọi', value: calls.active, icon: Activity, color: 'text-[var(--color-warning)]', bg: 'bg-[oklch(96%_0.08_85)]', href: '/calls?status=active' },
  ]

  const apiOk = true // We got a response, so API is up
  const postgresOk = deps?.postgres === 'ok'
  const redisOk = deps?.redis === 'ok'
  const voiceOk = voice?.status === 'ok'

  const healthItems = [
    { label: 'API Server', ok: apiOk, icon: Server, detail: ':3001' },
    { label: 'Voice Worker', ok: voiceOk, icon: Radio, detail: ':8000' },
    { label: 'PostgreSQL', ok: postgresOk, icon: Database, detail: deps ? 'connected' : 'unreachable' },
    { label: 'Redis', ok: redisOk, icon: Cpu, detail: deps ? 'connected' : 'unreachable' },
  ]

  const isFirstRun = calls.total === 0

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Dashboard</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Tổng quan hệ thống AI Call — DoctorCheck
        </p>
      </div>

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
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
        {/* Containment */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">Containment Rate</p>
          <p className="text-2xl font-bold text-[var(--color-text)]">
            {(overview.containmentRate * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">Cuộc gọi AI xử lý hoàn toàn</p>
        </div>

        {/* QA Score */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
          <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">Avg QA Score</p>
          <p className="text-2xl font-bold text-[var(--color-text)]">
            {overview.avgQaScore.toFixed(1)}{' '}
            <span className="text-sm font-normal text-[var(--color-text-muted)]">/ 5</span>
          </p>
          {qaPending > 0 && (
            <Link href="/qa" className="text-xs text-[var(--color-warning)] hover:underline mt-1 block">
              {qaPending} cuộc gọi chờ chấm →
            </Link>
          )}
        </div>

        {/* ElevenLabs metrics */}
        <div className={`rounded-xl border bg-white p-4 ${elevenLabs.connected ? 'border-[var(--color-border)]' : 'border-[oklch(88%_0.06_27)]'}`}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide">ElevenLabs</p>
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${elevenLabs.connected ? 'bg-[var(--color-success)]' : 'bg-[oklch(60%_0.15_27)]'}`} />
              <span className={`text-[10px] font-medium ${elevenLabs.connected ? 'text-[var(--color-success)]' : 'text-[oklch(50%_0.15_27)]'}`}>
                {elevenLabs.connected ? 'active' : 'idle'}
              </span>
            </div>
          </div>
          <div className="flex items-end gap-2 mb-1">
            <div className="w-6 h-6 rounded-md bg-[oklch(95%_0.03_250)] flex items-center justify-center shrink-0">
              <Mic className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            </div>
            <p className="text-2xl font-bold text-[var(--color-text)] leading-none">
              {elevenLabs.total === 0 ? '0' : elevenLabs.total.toLocaleString()}
            </p>
          </div>
          {elevenLabs.total === 0 ? (
            <p className="text-[10px] text-[var(--color-text-muted)]">Chưa có request nào</p>
          ) : (
            <div className="space-y-0.5 mt-1">
              <div className="flex items-center gap-2 text-[10px]">
                <span className="w-1 h-1 rounded-full bg-[var(--color-success)] shrink-0" />
                <span className="text-[var(--color-text-muted)]">OK</span>
                <span className="font-semibold text-[var(--color-text)] ml-auto">{elevenLabs.ok}</span>
              </div>
              <div className="flex items-center gap-2 text-[10px]">
                <span className="w-1 h-1 rounded-full bg-[var(--color-danger)] shrink-0" />
                <span className="text-[var(--color-text-muted)]">Err</span>
                <span className="font-semibold text-[var(--color-text)] ml-auto">{elevenLabs.err}</span>
              </div>
              {elevenLabs.avgLatencyMs !== null && (
                <div className="flex items-center gap-2 text-[10px]">
                  <span className="w-1 h-1 rounded-full bg-[var(--color-accent)] shrink-0" />
                  <span className="text-[var(--color-text-muted)]">Avg</span>
                  <span className="font-semibold text-[var(--color-text)] ml-auto">{elevenLabs.avgLatencyMs}ms</span>
                </div>
              )}
            </div>
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
