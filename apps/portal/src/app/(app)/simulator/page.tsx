import { Cpu } from 'lucide-react'
import { serverFetch } from '@/lib/api/server'
import { SimulatorClient } from './SimulatorClient'

interface VersionSummary {
  id: string
  version: string
  body: Record<string, unknown>
  status: string
}

interface Campaign {
  id: string
  name: string
  direction: 'inbound' | 'outbound'
  publishedVersionId: string | null
  versions?: VersionSummary[]
}

async function fetchCampaignsWithVersions(): Promise<Campaign[]> {
  try {
    const campaigns = await serverFetch<Campaign[]>('/scripts')
    const withVersions = await Promise.all(
      campaigns.map(async (c) => {
        try {
          const versions = await serverFetch<VersionSummary[]>(`/scripts/${c.id}/versions`)
          return { ...c, versions }
        } catch {
          return { ...c, versions: [] }
        }
      })
    )
    return withVersions
  } catch {
    return []
  }
}

export default async function SimulatorPage() {
  const campaigns = await fetchCampaignsWithVersions()

  return (
    <div className="p-6 max-w-7xl mx-auto h-full">
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[oklch(95%_0.04_270)] flex items-center justify-center">
            <Cpu className="w-5 h-5 text-[oklch(50%_0.18_270)]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--color-text)] tracking-tight">Call Simulator</h1>
            <p className="text-xs text-[var(--color-text-muted)]">Giả lập cuộc gọi AI — không cần audio, không cần CloudFone</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[oklch(55%_0.16_145)]" />
            Mock mode — beat text only
          </span>
        </div>
      </div>

      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center text-[var(--color-text-muted)]">
          <Cpu className="w-10 h-10 mb-3 opacity-20" />
          <p className="text-sm">Chưa có campaign nào. Tạo và publish một script trước.</p>
        </div>
      ) : (
        <SimulatorClient campaigns={campaigns} />
      )}
    </div>
  )
}
