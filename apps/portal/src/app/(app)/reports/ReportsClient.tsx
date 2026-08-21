'use client'

import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'

type QuickRange = 'today' | '7d' | '30d' | 'custom'

interface DayData { date: string; total: number; completed: number; handoff: number; error: number }
interface QaTrend { week: string; avgScore: number; count: number }
interface DurationStat { campaignId: string | null; status: string; avgSeconds: number; count: number }

function BarChart({ data, valueKey, color, label }: {
  data: Array<Record<string, unknown>>
  valueKey: string
  color: string
  label: string
}) {
  const values = data.map((d) => Number(d[valueKey] ?? 0))
  const max = Math.max(...values, 1)
  const W = 480
  const H = 120
  const BAR_W = Math.max(4, Math.min(24, Math.floor((W - 32) / Math.max(data.length, 1)) - 4))
  const gap = Math.floor((W - 32) / Math.max(data.length, 1))

  return (
    <div>
      <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-3">{label}</p>
      {data.length === 0 ? (
        <div className="h-[120px] flex items-center justify-center text-xs text-[var(--color-text-muted)] bg-[var(--color-surface-overlay)] rounded-lg">
          Chưa có dữ liệu
        </div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
          {values.map((v, i) => {
            const barH = Math.max(2, Math.floor((v / max) * (H - 20)))
            const x = 16 + i * gap + (gap - BAR_W) / 2
            return (
              <g key={i}>
                <rect
                  x={x} y={H - 16 - barH}
                  width={BAR_W} height={barH}
                  rx={2} fill={color} opacity="0.85"
                />
                <title>{`${String(data[i]['date'] ?? data[i]['week'] ?? i)}: ${v}`}</title>
              </g>
            )
          })}
          <line x1={16} y1={H - 16} x2={W - 16} y2={H - 16} stroke="var(--color-border)" strokeWidth={1} />
        </svg>
      )}
    </div>
  )
}

function fmt(s: number) {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}m${String(sec).padStart(2, '0')}s`
}

function toISODate(d: Date) {
  return d.toISOString().split('T')[0]
}

function rangeForQuick(q: QuickRange): { from: string; to: string } {
  const now = new Date()
  const to = toISODate(now)
  if (q === 'today') return { from: to, to }
  if (q === '7d') { const d = new Date(now); d.setDate(d.getDate() - 7); return { from: toISODate(d), to } }
  if (q === '30d') { const d = new Date(now); d.setDate(d.getDate() - 30); return { from: toISODate(d), to } }
  return { from: to, to }
}

interface Props {
  initialCallsByDay: DayData[]
  initialQaTrends: QaTrend[]
  initialDuration: DurationStat[]
}

export function ReportsClient({ initialCallsByDay, initialQaTrends, initialDuration }: Props) {
  const [quick, setQuick] = useState<QuickRange>('30d')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [callsByDay, setCallsByDay] = useState(initialCallsByDay)
  const [qaTrends, setQaTrends] = useState(initialQaTrends)
  const [duration, setDuration] = useState(initialDuration)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)

  function getRange() {
    if (quick === 'custom') return { from: customFrom, to: customTo }
    return rangeForQuick(quick)
  }

  async function fetchData(from: string, to: string) {
    setLoading(true)
    try {
      const [cbd, qat, dur] = await Promise.all([
        fetch(`/api/v1/analytics/calls-by-day?from=${from}&to=${to}`).then((r) => r.json()),
        fetch(`/api/v1/analytics/qa-trends?from=${from}&to=${to}`).then((r) => r.json()),
        fetch(`/api/v1/analytics/duration?from=${from}&to=${to}`).then((r) => r.json()),
      ])
      setCallsByDay(cbd as DayData[])
      setQaTrends(qat as QaTrend[])
      setDuration(dur as DurationStat[])
    } finally {
      setLoading(false)
    }
  }

  async function handleQuickSelect(q: QuickRange) {
    setQuick(q)
    if (q !== 'custom') {
      const { from, to } = rangeForQuick(q)
      await fetchData(from, to)
    }
  }

  async function handleCustomApply() {
    if (customFrom && customTo) await fetchData(customFrom, customTo)
  }

  async function handleExport() {
    setExporting(true)
    try {
      const { from, to } = getRange()
      const res = await fetch(`/api/v1/analytics/export?from=${from}&to=${to}`, { credentials: 'include' })
      if (!res.ok) return
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `analytics_${from}_${to}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  const totalCalls = callsByDay.reduce((a, d) => a + d.total, 0)
  const avgScore = qaTrends.length
    ? (qaTrends.reduce((a, t) => a + t.avgScore * t.count, 0) / qaTrends.reduce((a, t) => a + t.count, 0)).toFixed(2)
    : '—'

  const { from: rangeFrom, to: rangeTo } = getRange()

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Báo cáo</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Analytics — {totalCalls} cuộc gọi · QA trung bình {avgScore}/5
        </p>
      </div>

      {/* Date range controls */}
      <div className="flex flex-wrap items-center gap-2 mb-6">
        {(['today', '7d', '30d', 'custom'] as QuickRange[]).map((q) => {
          const labels: Record<QuickRange, string> = { today: 'Hôm nay', '7d': '7 ngày', '30d': '30 ngày', custom: 'Tùy chỉnh' }
          return (
            <button
              key={q}
              onClick={() => void handleQuickSelect(q)}
              className={[
                'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                quick === q
                  ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                  : 'bg-white text-[var(--color-text)] border-[var(--color-border)] hover:bg-[var(--color-surface-overlay)]',
              ].join(' ')}
            >
              {labels[q]}
            </button>
          )
        })}

        {quick === 'custom' && (
          <>
            <input
              type="date"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
              className="input text-xs py-1.5 max-w-[140px]"
            />
            <span className="text-xs text-[var(--color-text-muted)]">→</span>
            <input
              type="date"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              className="input text-xs py-1.5 max-w-[140px]"
            />
            <button
              onClick={() => void handleCustomApply()}
              disabled={!customFrom || !customTo}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-accent)] text-white border border-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            >
              Áp dụng
            </button>
          </>
        )}

        <div className="ml-auto flex items-center gap-2">
          {loading && <Loader2 className="w-4 h-4 animate-spin text-[var(--color-text-muted)]" />}
          <span className="text-xs text-[var(--color-text-muted)]">{rangeFrom} → {rangeTo}</span>
          <button
            onClick={() => void handleExport()}
            disabled={exporting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)] disabled:opacity-50 transition-colors"
          >
            {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            Export XLSX
          </button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Calls by day */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-5">
          <BarChart
            data={callsByDay as unknown as Array<Record<string, unknown>>}
            valueKey="total"
            color="oklch(55% 0.2 250)"
            label={`Cuộc gọi theo ngày`}
          />
          <div className="mt-3 flex gap-4 text-xs text-[var(--color-text-muted)]">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[oklch(55%_0.18_145)]" />Completed {callsByDay.reduce((a, d) => a + d.completed, 0)}</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[oklch(55%_0.14_250)]" />Handoff {callsByDay.reduce((a, d) => a + d.handoff, 0)}</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[oklch(52%_0.22_27)]" />Error {callsByDay.reduce((a, d) => a + d.error, 0)}</span>
          </div>
        </div>

        {/* QA trends */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-5">
          <BarChart
            data={qaTrends.map((t) => ({ ...t, date: t.week })) as unknown as Array<Record<string, unknown>>}
            valueKey="avgScore"
            color="oklch(72% 0.19 85)"
            label="Điểm QA trung bình theo tuần"
          />
          <div className="mt-3 text-xs text-[var(--color-text-muted)]">
            {qaTrends.length} tuần có dữ liệu · {qaTrends.reduce((a, t) => a + t.count, 0)} lượt chấm
          </div>
        </div>

        {/* Duration table */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-5 md:col-span-2">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">
            Thời lượng trung bình theo campaign & trạng thái
          </p>
          {duration.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)] text-center py-8">Chưa có dữ liệu</p>
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left pb-2 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Campaign</th>
                  <th className="text-left pb-2 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Trạng thái</th>
                  <th className="text-right pb-2 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">TB</th>
                  <th className="text-right pb-2 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Số cuộc</th>
                </tr>
              </thead>
              <tbody>
                {duration.map((d, i) => (
                  <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2.5 text-xs font-mono text-[var(--color-text-muted)]">
                      {d.campaignId ? d.campaignId.slice(0, 8) + '…' : '—'}
                    </td>
                    <td className="py-2.5 text-xs">{d.status}</td>
                    <td className="py-2.5 text-xs text-right font-medium">{fmt(d.avgSeconds)}</td>
                    <td className="py-2.5 text-xs text-right text-[var(--color-text-muted)]">{d.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
