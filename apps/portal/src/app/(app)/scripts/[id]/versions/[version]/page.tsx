import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import type { ScriptVersion, VersionStatus } from '@/lib/api/scripts'
import { serverFetch } from '@/lib/api/server'

async function fetchVersion(campaignId: string, version: string): Promise<ScriptVersion | null> {
  try {
    const versions = await serverFetch<ScriptVersion[]>(`/scripts/${campaignId}/versions`)
    return versions.find((v) => v.version === version) ?? null
  } catch {
    return null
  }
}

const STATUS_LABELS: Record<VersionStatus, string> = {
  draft: 'Draft',
  under_review: 'Under Review',
  published: 'Published',
  archived: 'Archived',
}

export default async function VersionDetailPage({
  params,
}: {
  params: Promise<{ id: string; version: string }>
}) {
  const { id, version } = await params
  const sv = await fetchVersion(id, version)
  if (!sv) notFound()

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Link
        href={`/scripts/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Campaign Detail
      </Link>

      <div className="flex items-center gap-3 mb-6">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
          v{sv.version}
        </h1>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
          {STATUS_LABELS[sv.status]}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8 text-sm">
        <MetaItem label="Created" value={new Date(sv.createdAt).toLocaleString('vi-VN')} />
        <MetaItem
          label="Published"
          value={sv.publishedAt ? new Date(sv.publishedAt).toLocaleString('vi-VN') : '—'}
        />
        <MetaItem label="Created by" value={sv.createdBy ?? '—'} />
      </div>

      {sv.reviewNote && (
        <div className="mb-6 p-4 rounded-lg bg-[oklch(97%_0.03_250)] border border-[oklch(88%_0.06_250)] text-sm text-[var(--color-text)]">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-1">
            Review Note
          </p>
          {sv.reviewNote}
        </div>
      )}

      <section>
        <h2 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
          Script Body
        </h2>
        <pre className="p-5 rounded-xl bg-[oklch(13%_0.02_250)] text-[oklch(82%_0.01_250)] text-xs font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap border border-[oklch(22%_0.04_250)]">
          {JSON.stringify(sv.body, null, 2)}
        </pre>
      </section>
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-white p-3">
      <p className="text-xs text-[var(--color-text-muted)] font-medium uppercase tracking-wide mb-1">
        {label}
      </p>
      <p className="text-sm font-medium text-[var(--color-text)] truncate">{value}</p>
    </div>
  )
}
