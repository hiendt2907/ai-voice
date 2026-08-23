'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Trash2, Brain, RefreshCw } from 'lucide-react'
import { ArticleForm } from '@/components/knowledge/ArticleForm'
import type { KnowledgeArticle, UpdateArticlePayload } from '@/lib/api/knowledge'

export default function EditArticlePage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [article, setArticle] = useState<KnowledgeArticle | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [reembedding, setReembedding] = useState(false)

  useEffect(() => {
    setLoadError(null)
    fetch(`/api/knowledge/${id}`)
      .then(async (r) => {
        if (!r.ok) {
          const body = (await r.json().catch(() => ({}))) as { message?: string }
          throw new Error(body.message ?? `Không thể tải bài viết (HTTP ${r.status})`)
        }
        return (await r.json()) as KnowledgeArticle
      })
      .then((data) => setArticle(data))
      .catch((err: unknown) => {
        // Load thất bại: KHÔNG được đẩy object lỗi vào form — tránh người dùng
        // vô tình bấm Lưu và ghi đè bài viết thật bằng dữ liệu rác.
        setLoadError(err instanceof Error ? err.message : 'Lỗi không xác định khi tải bài viết')
      })
      .finally(() => setLoading(false))
  }, [id])

  async function handleUpdate(data: UpdateArticlePayload) {
    const res = await fetch(`/api/knowledge/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.message ?? `Lỗi ${res.status}`)
    }
    router.push(`/knowledge/${id}`)
  }

  async function handleDelete() {
    if (!confirm('Xoá bài viết này?')) return
    setDeleteError(null)
    try {
      const res = await fetch(`/api/knowledge/${id}`, { method: 'DELETE' })
      if (!res.ok && res.status !== 204) {
        const body = (await res.json().catch(() => ({}))) as { message?: string }
        throw new Error(body.message ?? `Không thể xoá bài viết (HTTP ${res.status})`)
      }
      router.push('/knowledge')
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Lỗi không xác định khi xoá bài viết')
    }
  }

  async function handleReembed() {
    if (!article) return
    setReembedding(true)
    try {
      await fetch(`/api/knowledge/${id}/embed`, { method: 'POST' })
    } finally {
      setReembedding(false)
    }
  }

  if (loading) {
    return (
      <div className="p-8 max-w-3xl mx-auto">
        <div className="h-8 w-48 rounded bg-[var(--color-border)] animate-pulse" />
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="p-8 max-w-3xl mx-auto">
        <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          {loadError}
        </p>
      </div>
    )
  }

  if (!article) {
    return (
      <div className="p-8 max-w-3xl mx-auto text-[var(--color-text-muted)]">
        Không tìm thấy bài viết.
      </div>
    )
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <Link
          href={`/knowledge/${id}`}
          className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          {article.title}
        </Link>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
              {article.title}
            </h1>
            <p className="text-sm text-[var(--color-text-muted)] mt-1">
              {article.embeddingJson ? (
                <span className="text-emerald-600">Đã embed RAG</span>
              ) : (
                <span className="text-amber-500">Chưa embed — chưa dùng được trong RAG</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => void handleReembed()}
              disabled={reembedding}
              title="Re-embed bài viết này"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-xs text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:opacity-50 transition-colors"
            >
              {reembedding ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Brain className="w-3.5 h-3.5" />
              )}
              Re-embed
            </button>
            <button
              onClick={() => void handleDelete()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-xs text-red-500 hover:border-red-300 hover:bg-red-50 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Xoá
            </button>
          </div>
        </div>
        {deleteError && (
          <p className="mt-3 text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {deleteError}
          </p>
        )}
      </div>

      <ArticleForm
        initialData={{
          title: article.title,
          category: article.category,
          tags: article.tags ?? [],
          questionVariants: article.questionVariants ?? [],
          answerText: article.answerText,
          answerMale: article.answerMale,
          answerFemale: article.answerFemale,
          confidenceThreshold: article.confidenceThreshold,
          isActive: article.isActive,
        }}
        onSubmit={handleUpdate}
        submitLabel="Cập nhật"
      />
    </div>
  )
}
