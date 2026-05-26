import Link from 'next/link'
import { notFound } from 'next/navigation'
import {
  ArrowLeft,
  Plus,
  CheckCircle2,
  Clock,
  FileText,
  Eye,
  Send,
  Globe,
} from 'lucide-react'
import type { Campaign, ScriptVersion, VersionStatus } from '@/lib/api/scripts'

async function fetchCampaign(id: string): Promise<Campaign | null> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1/scripts/${id}`,
      { cache: 'no-store' },
    )
    if (res.status === 404) return null
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

async function fetchVersions(id: string): Promise<ScriptVersion[]> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1/scripts/${id}/versions`,
      { cache: 'no-store' },
    )
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export default async function CampaignDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const [campaign, versions] = await Promise.all([fetchCampaign(id), fetchVersions(id)])
  if (!campaign) notFound()

  const published = versions.find((v) => v.status === 'published')

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Breadcrumb */}
      <Link
        href="/scripts"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Script CMS
      </Link>

      {/* Campaign header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
              {campaign.name}
            </h1>
            {campaign.isActive && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border border-[oklch(88%_0.09_145)]">
                <CheckCircle2 className="w-3 h-3" />
                Live
              </span>
            )}
          </div>
          <p className="text-sm text-[var(--color-text-muted)]">
            {campaign.direction === 'inbound' ? 'Inbound' : 'Outbound'} · {campaign.voiceProfile}
          </p>
        </div>
        <Link
          href={`/scripts/${id}/new-version`}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] transition-colors"
        >
          <Plus className="w-4 h-4" />
          Tạo Version
        </Link>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard label="Versions" value={versions.length.toString()} />
        <StatCard label="Published" value={published?.version ?? '—'} highlight={!!published} />
        <StatCard
          label="Last Updated"
          value={new Date(campaign.updatedAt).toLocaleDateString('vi-VN')}
        />
      </div>

      {/* Version history */}
      <section>
        <h2 className="text-sm font-semibold text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
          Version History
        </h2>

        {versions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 rounded-xl border border-dashed border-[var(--color-border)] text-center">
            <FileText className="w-8 h-8 text-[var(--color-border)] mb-3" />
            <p className="text-sm text-[var(--color-text-muted)]">Chưa có version nào</p>
            <Link
              href={`/scripts/${id}/new-version`}
              className="mt-4 text-sm text-[var(--color-accent)] font-medium hover:underline"
            >
              Tạo version đầu tiên →
            </Link>
          </div>
        ) : (
          <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[oklch(97%_0.005_250)] border-b border-[var(--color-border)]">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">
                    Version
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">
                    Tạo lúc
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">
                    Published
                  </th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {versions.map((v) => (
                  <VersionRow key={v.id} version={v} campaignId={id} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function VersionRow({ version, campaignId }: { version: ScriptVersion; campaignId: string }) {
  return (
    <tr className="hover:bg-[oklch(98.5%_0.003_250)] transition-colors">
      <td className="px-4 py-3.5 font-mono text-sm font-medium text-[var(--color-text)]">
        v{version.version}
      </td>
      <td className="px-4 py-3.5">
        <StatusBadge status={version.status} />
      </td>
      <td className="px-4 py-3.5 text-[var(--color-text-muted)] text-xs">
        <span className="flex items-center gap-1.5">
          <Clock className="w-3 h-3" />
          {new Date(version.createdAt).toLocaleString('vi-VN')}
        </span>
      </td>
      <td className="px-4 py-3.5 text-[var(--color-text-muted)] text-xs">
        {version.publishedAt ? new Date(version.publishedAt).toLocaleDateString('vi-VN') : '—'}
      </td>
      <td className="px-4 py-3.5">
        <div className="flex items-center justify-end gap-2">
          <Link
            href={`/scripts/${campaignId}/versions/${version.version}`}
            className="p-1.5 rounded hover:bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
            title="View script body"
          >
            <Eye className="w-3.5 h-3.5" />
          </Link>
          {version.status === 'draft' && (
            <span
              className="p-1.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:bg-[var(--color-surface-overlay)] transition-colors cursor-pointer"
              title="Submit for review"
            >
              <Send className="w-3.5 h-3.5" />
            </span>
          )}
          {version.status === 'under_review' && (
            <span
              className="p-1.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-success)] hover:bg-[var(--color-surface-overlay)] transition-colors cursor-pointer"
              title="Publish"
            >
              <Globe className="w-3.5 h-3.5" />
            </span>
          )}
        </div>
      </td>
    </tr>
  )
}

const STATUS_STYLES: Record<VersionStatus, string> = {
  draft: 'bg-[oklch(95%_0.01_250)] text-[oklch(42%_0.04_250)] border-[oklch(85%_0.04_250)]',
  under_review:
    'bg-[oklch(96%_0.08_85)] text-[oklch(42%_0.18_85)] border-[oklch(88%_0.12_85)]',
  published:
    'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border-[oklch(88%_0.09_145)]',
  archived: 'bg-[oklch(93%_0.005_0)] text-[oklch(48%_0.02_0)] border-[oklch(85%_0.01_0)]',
}

const STATUS_LABELS: Record<VersionStatus, string> = {
  draft: 'Draft',
  under_review: 'Under Review',
  published: 'Published',
  archived: 'Archived',
}

function StatusBadge({ status }: { status: VersionStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

function StatCard({
  label,
  value,
  highlight,
}: {
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
      <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">
        {label}
      </p>
      <p
        className={`text-xl font-semibold tracking-tight ${highlight ? 'text-[var(--color-success)]' : 'text-[var(--color-text)]'}`}
      >
        {value}
      </p>
    </div>
  )
}
