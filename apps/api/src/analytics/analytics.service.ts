import { Injectable } from '@nestjs/common'
import { InjectDataSource } from '@nestjs/typeorm'
import { DataSource } from 'typeorm'
import Redis from 'ioredis'

let _analyticsRedis: Redis | null = null
function getAnalyticsRedis(): Redis {
  if (!_analyticsRedis) {
    _analyticsRedis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379', {
      lazyConnect: true,
      connectTimeout: 2000,
      maxRetriesPerRequest: 0,
    })
  }
  return _analyticsRedis
}

export interface ElevenLabsMetrics {
  total: number
  ok: number
  err: number
  avgLatencyMs: number | null
  lastSuccessTs: number | null
  connected: boolean
}

interface CallsByDayRow {
  date: string
  status: string
  count: string
}
interface QaTrendRow {
  week: string
  avg: string
  count: string
}
interface StatusRow {
  status: string
  count: string
}
interface DurationRow {
  'campaignId': string | null
  status: string
  avg: string
  count: string
}
interface AvgRow {
  avg: string | null
}

@Injectable()
export class AnalyticsService {
  constructor(@InjectDataSource() private readonly ds: DataSource) {}

  async getOverview() {
    const statusRows = await this.ds.query<StatusRow[]>(
      `SELECT status, COUNT(*)::int::text as count FROM call_sessions GROUP BY status`,
    )
    const counts: Record<string, number> = {}
    for (const r of statusRows) counts[r.status] = parseInt(r.count, 10)

    const total = Object.values(counts).reduce((a, b) => a + b, 0)
    const completed = counts['completed'] ?? 0
    const handoff = counts['handoff'] ?? 0
    const error = counts['error'] ?? 0
    const active = counts['active'] ?? 0

    const qaRows = await this.ds.query<AvgRow[]>(
      `SELECT ROUND(AVG(score)::numeric, 2)::float::text as avg FROM qa_scores`,
    )
    const avgQaScore = parseFloat(qaRows[0]?.avg ?? '0') || 0
    const denom = completed + handoff
    const containmentRate = denom > 0 ? Math.round((completed / denom) * 100) / 100 : 0

    return {
      calls: { total, completed, handoff, error, active },
      period: 'all',
      containmentRate,
      avgQaScore,
    }
  }

  private dateFilter(from?: string, to?: string, col = '"createdAt"'): { clause: string; params: string[] } {
    const conditions: string[] = []
    const params: string[] = []
    if (from) { conditions.push(`${col} >= $${params.length + 1}::date`); params.push(from) }
    if (to) { conditions.push(`${col} < ($${params.length + 1}::date + INTERVAL '1 day')`); params.push(to) }
    if (!conditions.length) {
      conditions.push(`${col} >= NOW() - INTERVAL '30 days'`)
    }
    return { clause: 'WHERE ' + conditions.join(' AND '), params }
  }

  async getCallsByDay(from?: string, to?: string) {
    const { clause, params } = this.dateFilter(from, to)
    const rows = await this.ds.query<CallsByDayRow[]>(`
      SELECT DATE("createdAt")::text as date, status, COUNT(*)::int::text as count
      FROM call_sessions
      ${clause}
      GROUP BY DATE("createdAt"), status
      ORDER BY date ASC
    `, params)
    const byDate = new Map<string, Record<string, number>>()
    for (const r of rows) {
      if (!byDate.has(r.date)) byDate.set(r.date, {})
      byDate.get(r.date)![r.status] = parseInt(r.count, 10)
    }
    return Array.from(byDate.entries()).map(([date, c]) => ({
      date,
      total: Object.values(c).reduce((a, b) => a + b, 0),
      completed: c['completed'] ?? 0,
      handoff: c['handoff'] ?? 0,
      error: c['error'] ?? 0,
    }))
  }

  async getQaTrends(from?: string, to?: string) {
    const { clause, params } = this.dateFilter(from, to)
    const rows = await this.ds.query<QaTrendRow[]>(`
      SELECT DATE_TRUNC('week', "createdAt")::date::text as week,
             ROUND(AVG(score)::numeric, 2)::float::text as avg,
             COUNT(*)::int::text as count
      FROM qa_scores
      ${clause}
      GROUP BY DATE_TRUNC('week', "createdAt")
      ORDER BY week ASC
    `, params)
    return rows.map((r) => ({
      week: r.week,
      avgScore: parseFloat(r.avg),
      count: parseInt(r.count, 10),
    }))
  }

  async getDurationStats(from?: string, to?: string) {
    const { clause, params } = this.dateFilter(from, to)
    const rows = await this.ds.query<DurationRow[]>(`
      SELECT "campaignId", status,
             ROUND(AVG("durationSeconds"))::int::text as avg,
             COUNT(*)::int::text as count
      FROM call_sessions
      ${clause}
      AND "durationSeconds" IS NOT NULL

      GROUP BY "campaignId", status
      ORDER BY count DESC
      LIMIT 20
    `, params)
    return rows.map((r) => ({
      campaignId: r['campaignId'],
      status: r.status,
      avgSeconds: parseInt(r.avg, 10),
      count: parseInt(r.count, 10),
    }))
  }

  async getElevenLabsMetrics(): Promise<ElevenLabsMetrics> {
    const HASH_KEY = 'elevenlabs:stats'
    const TEN_MINUTES_MS = 10 * 60 * 1000

    try {
      const redis = getAnalyticsRedis()
      const raw = await redis.hgetall(HASH_KEY)

      const total = parseInt(raw['total'] ?? '0', 10) || 0
      const ok = parseInt(raw['ok'] ?? '0', 10) || 0
      const err = parseInt(raw['err'] ?? '0', 10) || 0
      const latencySum = parseFloat(raw['latency_ms_sum'] ?? '0') || 0
      const lastSuccessTs = raw['last_success_ts'] ? parseFloat(raw['last_success_ts']) : null

      const avgLatencyMs = ok > 0 ? Math.round(latencySum / ok) : null
      const connected = lastSuccessTs !== null && Date.now() - lastSuccessTs < TEN_MINUTES_MS

      return { total, ok, err, avgLatencyMs, lastSuccessTs, connected }
    } catch {
      return { total: 0, ok: 0, err: 0, avgLatencyMs: null, lastSuccessTs: null, connected: false }
    }
  }

  async exportXlsx(from?: string, to?: string): Promise<Buffer> {
    const [callsByDay, qaTrends, duration] = await Promise.all([
      this.getCallsByDay(from, to),
      this.getQaTrends(from, to),
      this.getDurationStats(from, to),
    ])

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const ExcelJS = require('exceljs') as typeof import('exceljs')
    const wb = new ExcelJS.Workbook()

    const sheet1 = wb.addWorksheet('Calls by Day')
    sheet1.addRow(['Ngày', 'Tổng', 'Hoàn thành', 'Handoff', 'Lỗi'])
    for (const d of callsByDay) sheet1.addRow([d.date, d.total, d.completed, d.handoff, d.error])

    const sheet2 = wb.addWorksheet('QA Trends')
    sheet2.addRow(['Tuần', 'Điểm TB', 'Số cuộc'])
    for (const t of qaTrends) sheet2.addRow([t.week, t.avgScore, t.count])

    const sheet3 = wb.addWorksheet('Duration')
    sheet3.addRow(['Campaign ID', 'Trạng thái', 'TB (giây)', 'Số cuộc'])
    for (const d of duration) sheet3.addRow([d.campaignId ?? '—', d.status, d.avgSeconds, d.count])

    return wb.xlsx.writeBuffer() as unknown as Promise<Buffer>
  }
}
