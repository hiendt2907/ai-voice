import { AppShell } from '@/components/AppShell'
import { serverFetch } from '@/lib/api/server'

interface MeResponse {
  sub: string
  email: string
  role: string
}

async function getUser(): Promise<MeResponse | null> {
  try {
    return await serverFetch<MeResponse>('/auth/me')
  } catch {
    return null
  }
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getUser()

  return <AppShell user={user}>{children}</AppShell>
}
