import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const apiBase = () =>
  `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1`

async function authHeader(): Promise<Record<string, string>> {
  const store = await cookies()
  const token = store.get('access_token')?.value
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const qs = searchParams.toString()
  const upstream = await fetch(`${apiBase()}/knowledge${qs ? `?${qs}` : ''}`, {
    headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
    cache: 'no-store',
  })
  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const upstream = await fetch(`${apiBase()}/knowledge`, {
    method: 'POST',
    headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}
