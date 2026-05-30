import { type NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const apiBase = process.env.API_INTERNAL_URL ?? 'http://localhost:3001'
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  const upstream = await fetch(`${apiBase}/api/v1/calls/${id}/recording/stream`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: 'no-store',
  })

  if (!upstream.ok) {
    return NextResponse.json({ error: 'Not found' }, { status: upstream.status })
  }

  const contentType = upstream.headers.get('content-type') ?? 'audio/wav'
  const contentLength = upstream.headers.get('content-length')

  const headers: Record<string, string> = {
    'Content-Type': contentType,
    'Accept-Ranges': 'bytes',
  }
  if (contentLength) headers['Content-Length'] = contentLength

  return new NextResponse(upstream.body, { status: 200, headers })
}
