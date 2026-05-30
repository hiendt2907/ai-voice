import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const apiBase = () => `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1`

async function authHeader(): Promise<Record<string, string>> {
  const store = await cookies()
  const token = store.get('access_token')?.value
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const upstream = await fetch(`${apiBase()}/nlu/documents/${id}`, {
    headers: { ...(await authHeader()) },
    cache: 'no-store',
  })
  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json()
  const upstream = await fetch(`${apiBase()}/nlu/documents/${id}`, {
    method: 'PATCH',
    headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const upstream = await fetch(`${apiBase()}/nlu/documents/${id}`, {
    method: 'DELETE',
    headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
  })
  if (upstream.status === 204) return new NextResponse(null, { status: 204 })
  const data = await upstream.json().catch(() => ({}))
  return NextResponse.json(data, { status: upstream.status })
}
