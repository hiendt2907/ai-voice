import { AppSidebar } from '@/components/AppSidebar'
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

  return (
    <div className="flex min-h-screen">
      <AppSidebar user={user} />
      <main className="flex-1 ml-[220px] min-h-screen bg-[var(--color-surface)] overflow-auto">
        {children}
      </main>
    </div>
  )
}
