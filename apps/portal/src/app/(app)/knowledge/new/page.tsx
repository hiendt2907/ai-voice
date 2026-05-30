'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { Suspense } from 'react'
import { ArticleForm } from '@/components/knowledge/ArticleForm'
import type { CreateArticlePayload, UpdateArticlePayload } from '@/lib/api/knowledge'

function NewArticleContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const scriptId = searchParams.get('scriptId')

  async function handleCreate(data: CreateArticlePayload | UpdateArticlePayload) {
    const payload = scriptId ? { ...data, scriptId } : data
    const res = await fetch('/api/knowledge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { message?: string }).message ?? `Lỗi ${res.status}`)
    }
    const article = await res.json() as { id: string }
    const back = scriptId ? `/scripts/${scriptId}` : `/knowledge/${article.id}`
    router.push(back)
  }

  const backHref = scriptId ? `/scripts/${scriptId}` : '/knowledge'
  const backLabel = scriptId ? 'Quay lại Script' : 'Knowledge Base'

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <Link
          href={backHref}
          className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          {backLabel}
        </Link>
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
          Thêm bài viết mới
        </h1>
        {scriptId && (
          <p className="text-sm text-[var(--color-accent)] mt-0.5">
            Sẽ được liên kết với script hiện tại
          </p>
        )}
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Q&A scripted — câu trả lời sẽ đọc trực tiếp qua TTS khi RAG match
        </p>
      </div>

      <ArticleForm onSubmit={handleCreate} submitLabel="Tạo bài viết" />
    </div>
  )
}

export default function NewArticlePage() {
  return (
    <Suspense>
      <NewArticleContent />
    </Suspense>
  )
}
