import Link from 'next/link'
import { Plus, BookOpen, CheckCircle2, XCircle, Brain } from 'lucide-react'
import type { KnowledgeArticle } from '@/lib/api/knowledge'
import { CATEGORY_LABELS } from '@/lib/api/knowledge'
import { serverFetch } from '@/lib/api/server'

async function fetchArticles(): Promise<KnowledgeArticle[]> {
  try {
    return await serverFetch<KnowledgeArticle[]>('/knowledge?all=true')
  } catch {
    return []
  }
}

export default async function KnowledgePage() {
  const articles = await fetchArticles()
  const active = articles.filter((a) => a.isActive).length
  const embedded = articles.filter((a) => a.embeddingJson).length

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
            Knowledge Base
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            {articles.length} bài viết · {active} active · {embedded} đã embed RAG
          </p>
        </div>
        <Link
          href="/knowledge/new"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] transition-colors duration-[var(--duration-fast)]"
        >
          <Plus className="w-4 h-4" />
          Thêm bài viết
        </Link>
      </div>

      {articles.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {articles.map((a) => (
            <ArticleCard key={a.id} article={a} />
          ))}
        </div>
      )}
    </div>
  )
}

function ArticleCard({ article }: { article: KnowledgeArticle }) {
  const categoryLabel = article.category ? (CATEGORY_LABELS[article.category] ?? article.category) : null

  return (
    <Link
      href={`/knowledge/${article.id}`}
      className="group flex flex-col gap-3 p-5 rounded-xl border border-[var(--color-border)] bg-white hover:border-[var(--color-accent)] hover:shadow-sm transition-all duration-[var(--duration-fast)]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <BookOpen className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
          <span className="text-sm font-semibold text-[var(--color-text)] truncate">
            {article.title}
          </span>
        </div>
        {article.isActive ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
        ) : (
          <XCircle className="w-4 h-4 text-[var(--color-text-muted)] shrink-0" />
        )}
      </div>

      {categoryLabel && (
        <span className="inline-flex self-start px-2 py-0.5 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] text-[11px] font-medium">
          {categoryLabel}
        </span>
      )}

      <p className="text-xs text-[var(--color-text-muted)] line-clamp-2 leading-relaxed">
        {article.answerText}
      </p>

      <div className="flex items-center justify-between pt-1 border-t border-[var(--color-border)]">
        <span className="text-[11px] text-[var(--color-text-muted)]">
          {article.questionVariants?.length ?? 0} câu hỏi mẫu
        </span>
        {article.embeddingJson ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600">
            <Brain className="w-3 h-3" />
            Embedded
          </span>
        ) : (
          <span className="text-[11px] text-amber-500">Chưa embed</span>
        )}
      </div>
    </Link>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <div className="w-16 h-16 rounded-2xl bg-[var(--color-surface-muted)] flex items-center justify-center">
        <BookOpen className="w-8 h-8 text-[var(--color-text-muted)]" />
      </div>
      <div>
        <p className="text-[var(--color-text)] font-medium">Chưa có bài viết nào</p>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Thêm bài viết Q&A để hệ thống RAG trả lời tự động
        </p>
      </div>
      <Link
        href="/knowledge/new"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-border)] text-sm font-medium text-[var(--color-text)] hover:border-[var(--color-accent)] transition-colors"
      >
        <Plus className="w-4 h-4" />
        Thêm bài viết đầu tiên
      </Link>
    </div>
  )
}
