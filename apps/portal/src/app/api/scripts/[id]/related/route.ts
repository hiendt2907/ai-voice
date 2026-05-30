import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const apiBase = () =>
  `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1`

async function authHeader(): Promise<Record<string, string>> {
  const store = await cookies()
  const token = store.get('access_token')?.value
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const upstream = await fetch(`${apiBase()}/scripts/${id}/related`, {
    headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
    cache: 'no-store',
  })
  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}
