import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Plus, Clock, FileText, Eye } from 'lucide-react'
import type { Campaign, ScriptVersion, VersionStatus } from '@/lib/api/scripts'
import type { KnowledgeArticle } from '@/lib/api/knowledge'
import type { NluDocument } from '@/lib/api/nlu'
import { serverFetch } from '@/lib/api/server'
import { VersionActions } from './VersionActions'
import { CampaignToggle } from './CampaignToggle'
import { DeleteCampaignButton } from './DeleteCampaignButton'
import ScriptResourcePanel from './ScriptResourcePanel'

interface RelatedData {
  kbArticles: KnowledgeArticle[]
  nluDocs: NluDocument[]
}

async function fetchCampaign(id: string): Promise<Campaign | null> {
  try {
    return await serverFetch<Campaign>(`/scripts/${id}`)
  } catch {
    return null
  }
}

async function fetchVersions(id: string): Promise<ScriptVersion[]> {
  try {
    return await serverFetch<ScriptVersion[]>(`/scripts/${id}/versions`)
  } catch {
    return []
  }
}

async function fetchRelated(id: string): Promise<RelatedData> {
  try {
    return await serverFetch<RelatedData>(`/scripts/${id}/related`)
  } catch {
    return { kbArticles: [], nluDocs: [] }
  }
}

export default async function CampaignDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ new?: string }>
}) {
  const { id } = await params
  const sp = await searchParams
  const isNew = sp.new === '1'
  const [campaign, versions, related] = await Promise.all([
    fetchCampaign(id),
    fetchVersions(id),
    fetchRelated(id),
  ])
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
            <CampaignToggle campaignId={id} isActive={campaign.isActive} />
          </div>
          <p className="text-sm text-[var(--color-text-muted)]">
            {campaign.direction === 'inbound' ? 'Inbound' : 'Outbound'} · {campaign.voiceProfile}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DeleteCampaignButton campaignId={id} campaignName={campaign.name} />
          <Link
            href={`/scripts/${id}/new-version`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            Tạo Version
          </Link>
        </div>
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

      {/* Script Resource Panel — KB + NLU */}
      <ScriptResourcePanel scriptId={id} initialData={related} isNew={isNew} />
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
          <VersionActions campaignId={campaignId} version={version.version} status={version.status} />
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
