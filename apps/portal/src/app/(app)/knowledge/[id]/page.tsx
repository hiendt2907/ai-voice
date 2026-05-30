import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Brain, Pencil, MessageSquare, User, Users, Tag, SlidersHorizontal } from 'lucide-react'
import type { KnowledgeArticle } from '@/lib/api/knowledge'
import { CATEGORY_LABELS } from '@/lib/api/knowledge'
import { serverFetch } from '@/lib/api/server'

async function fetchArticle(id: string): Promise<KnowledgeArticle | null> {
  try {
    return await serverFetch<KnowledgeArticle>(`/knowledge/${id}`)
  } catch {
    return null
  }
}

export default async function ArticleDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const article = await fetchArticle(id)
  if (!article) notFound()

  const categoryLabel = article.category ? (CATEGORY_LABELS[article.category] ?? article.category) : null

  return (
    <div className="p-8 max-w-3xl mx-auto">
      {/* Breadcrumb */}
      <Link
        href="/knowledge"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Knowledge Base
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
              {article.title}
            </h1>
            {article.isActive ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border border-[oklch(88%_0.09_145)]">
                Active
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[oklch(93%_0.005_0)] text-[oklch(48%_0.02_0)] border border-[oklch(85%_0.01_0)]">
                Inactive
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {categoryLabel && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] text-[11px] font-medium">
                {categoryLabel}
              </span>
            )}
            {article.embeddingJson ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600">
                <Brain className="w-3 h-3" />
                Đã embed RAG
              </span>
            ) : (
              <span className="text-[11px] text-amber-500">Chưa embed</span>
            )}
          </div>
        </div>
        <Link
          href={`/knowledge/${id}/edit`}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-xs font-medium text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors shrink-0"
        >
          <Pencil className="w-3.5 h-3.5" />
          Chỉnh sửa
        </Link>
      </div>

      <div className="space-y-5">
        {/* Question variants */}
        <Section icon={<MessageSquare className="w-4 h-4" />} label="Câu hỏi mẫu">
          <ol className="space-y-1.5">
            {article.questionVariants.map((q, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="shrink-0 w-5 h-5 rounded-full bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] text-[10px] font-semibold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <span className="text-sm text-[var(--color-text)]">{q}</span>
              </li>
            ))}
          </ol>
        </Section>

        {/* Answer text */}
        <Section icon={<Users className="w-4 h-4" />} label="Câu trả lời (mặc định)">
          <p className="text-sm text-[var(--color-text)] leading-relaxed">{article.answerText}</p>
        </Section>

        {/* Gender answers */}
        {(article.answerMale || article.answerFemale) && (
          <div className="grid grid-cols-2 gap-3">
            {article.answerMale && (
              <Section icon={<User className="w-4 h-4" />} label="Câu trả lời (Nam)">
                <p className="text-sm text-[var(--color-text)] leading-relaxed">{article.answerMale}</p>
              </Section>
            )}
            {article.answerFemale && (
              <Section icon={<User className="w-4 h-4" />} label="Câu trả lời (Nữ)">
                <p className="text-sm text-[var(--color-text)] leading-relaxed">{article.answerFemale}</p>
              </Section>
            )}
          </div>
        )}

        {/* Tags + threshold */}
        <div className="grid grid-cols-2 gap-3">
          {article.tags && article.tags.length > 0 && (
            <Section icon={<Tag className="w-4 h-4" />} label="Tags">
              <div className="flex flex-wrap gap-1.5">
                {article.tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex px-2 py-0.5 rounded-md bg-[oklch(96%_0.08_250)] text-[oklch(42%_0.12_250)] text-[11px] font-medium"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </Section>
          )}

          <Section icon={<SlidersHorizontal className="w-4 h-4" />} label="Ngưỡng tin cậy">
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-[var(--color-border)]">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${article.confidenceThreshold * 100}%` }}
                />
              </div>
              <span className="text-sm font-semibold text-[var(--color-text)] tabular-nums">
                {(article.confidenceThreshold * 100).toFixed(0)}%
              </span>
            </div>
          </Section>
        </div>

        {/* Meta */}
        <div className="pt-4 border-t border-[var(--color-border)] flex items-center gap-6 text-[11px] text-[var(--color-text-muted)]">
          <span>Tạo: {new Date(article.createdAt).toLocaleString('vi-VN')}</span>
          <span>Cập nhật: {new Date(article.updatedAt).toLocaleString('vi-VN')}</span>
        </div>
      </div>
    </div>
  )
}

function Section({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white p-4">
      <div className="flex items-center gap-1.5 mb-3 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">
        {icon}
        {label}
      </div>
      {children}
    </div>
  )
}
