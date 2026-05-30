import { cookies } from 'next/headers'

const API_BASE = `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1`

export async function serverFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const store = await cookies()
  const token = store.get('access_token')?.value

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers as Record<string, string> | undefined),
    },
    cache: 'no-store',
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }

  return res.json() as Promise<T>
}
