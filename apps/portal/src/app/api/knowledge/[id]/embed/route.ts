import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const apiBase = () =>
  `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1`

async function authHeader(): Promise<Record<string, string>> {
  const store = await cookies()
  const token = store.get('access_token')?.value
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  // Fetch the article to get questionVariants, then trigger embed via voice worker through the API
  const articleRes = await fetch(`${apiBase()}/knowledge/${id}`, {
    headers: await authHeader(),
    cache: 'no-store',
  })
  if (!articleRes.ok) {
    return NextResponse.json({ message: 'Bài viết không tồn tại' }, { status: 404 })
  }
  const article = await articleRes.json() as { questionVariants?: string[] }
  const texts = article.questionVariants ?? []

  // Trigger re-embed via voice worker
  const voiceUrl = process.env.VOICE_WORKER_URL ?? 'http://localhost:8001'
  try {
    await fetch(`${voiceUrl}/rag/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ article_id: id, texts }),
    })
  } catch {
    return NextResponse.json({ message: 'Voice worker không phản hồi' }, { status: 502 })
  }

  return NextResponse.json({ ok: true })
}
