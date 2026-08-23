// Khớp cách ghép URL với lib/api/server.ts — biến môi trường trong cluster
// (deploy/k8s/config/configmap.yaml) là API_INTERNAL_URL=http://api:3001, KHÔNG có /api/v1.
const API_BASE = `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1`

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string>),
    },
    cache: 'no-store',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}
