import Link from 'next/link'
import { Plus, Mic2, PhoneIncoming, PhoneOutgoing, CheckCircle2, Clock } from 'lucide-react'
import type { Campaign } from '@/lib/api/scripts'
import { serverFetch } from '@/lib/api/server'

async function fetchCampaigns(): Promise<Campaign[]> {
  try {
    return await serverFetch<Campaign[]>('/scripts')
  } catch {
    return []
  }
}

export default async function ScriptsPage() {
  const campaigns = await fetchCampaigns()

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
            Script CMS
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            Quản lý kịch bản cuộc gọi AI — {campaigns.length} campaign
          </p>
        </div>
        <Link
          href="/scripts/new"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] transition-colors duration-[var(--duration-fast)]"
        >
          <Plus className="w-4 h-4" />
          Tạo Campaign
        </Link>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {campaigns.map((c) => (
            <CampaignCard key={c.id} campaign={c} />
          ))}
        </div>
      )}
    </div>
  )
}

function CampaignCard({ campaign }: { campaign: Campaign }) {
  const DirectionIcon = campaign.direction === 'inbound' ? PhoneIncoming : PhoneOutgoing
  const directionLabel = campaign.direction === 'inbound' ? 'Inbound' : 'Outbound'

  return (
    <Link
      href={`/scripts/${campaign.id}`}
      className="group flex flex-col gap-4 p-5 rounded-xl border border-[var(--color-border)] bg-white hover:border-[var(--color-accent)] hover:shadow-sm transition-all duration-[var(--duration-fast)]"
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-[var(--color-text)] text-sm leading-snug truncate group-hover:text-[var(--color-accent)] transition-colors">
            {campaign.name}
          </h3>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5 truncate">
            {campaign.voiceProfile}
          </p>
        </div>
        {campaign.isActive && (
          <span className="shrink-0 flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border border-[oklch(88%_0.09_145)]">
            <CheckCircle2 className="w-2.5 h-2.5" />
            Live
          </span>
        )}
      </div>

      {/* Direction badge */}
      <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
        <DirectionIcon className="w-3.5 h-3.5" />
        {directionLabel}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)] pt-2 border-t border-[var(--color-border)]">
        <Clock className="w-3 h-3" />
        {new Date(campaign.updatedAt).toLocaleDateString('vi-VN')}
      </div>
    </Link>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-14 h-14 rounded-2xl bg-[oklch(96%_0.02_250)] flex items-center justify-center mb-4">
        <Mic2 className="w-7 h-7 text-[var(--color-accent)]" />
      </div>
      <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">
        Chưa có campaign nào
      </h3>
      <p className="text-sm text-[var(--color-text-muted)] max-w-xs mb-6">
        Tạo campaign đầu tiên để bắt đầu quản lý kịch bản AI Call
      </p>
      <Link
        href="/scripts/new"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] transition-colors"
      >
        <Plus className="w-4 h-4" />
        Tạo Campaign
      </Link>
    </div>
  )
}
