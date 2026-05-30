import { serverFetch } from '@/lib/api/server'
import { ReportsClient } from './ReportsClient'

interface DayData { date: string; total: number; completed: number; handoff: number; error: number }
interface QaTrend { week: string; avgScore: number; count: number }
interface DurationStat { campaignId: string | null; status: string; avgSeconds: number; count: number }

async function fetchCallsByDay(): Promise<DayData[]> {
  try { return await serverFetch<DayData[]>('/analytics/calls-by-day') }
  catch { return [] }
}
async function fetchQaTrends(): Promise<QaTrend[]> {
  try { return await serverFetch<QaTrend[]>('/analytics/qa-trends') }
  catch { return [] }
}
async function fetchDuration(): Promise<DurationStat[]> {
  try { return await serverFetch<DurationStat[]>('/analytics/duration') }
  catch { return [] }
}

export default async function ReportsPage() {
  const [callsByDay, qaTrends, duration] = await Promise.all([
    fetchCallsByDay(),
    fetchQaTrends(),
    fetchDuration(),
  ])

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <ReportsClient
        initialCallsByDay={callsByDay}
        initialQaTrends={qaTrends}
        initialDuration={duration}
      />
    </div>
  )
}
