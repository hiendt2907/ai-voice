'use client'

import { useState } from 'react'
import { Menu, Mic2 } from 'lucide-react'
import { AppSidebar } from './AppSidebar'

interface User {
  email: string
  role: string
}

interface AppShellProps {
  user: User | null
  children: React.ReactNode
}

/**
 * Responsive app frame: fixed sidebar on desktop (md+), off-canvas drawer
 * with a mobile top bar below that. State lives here (not in AppSidebar)
 * because the hamburger trigger and the sidebar itself are visually
 * separate components that both need it, and the layout above this is a
 * Server Component that can't hold client state itself.
 */
export function AppShell({ user, children }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="min-h-screen">
      <header className="md:hidden sticky top-0 z-30 flex items-center gap-3 h-14 px-4 bg-[oklch(12%_0.025_250)] border-b border-[oklch(20%_0.04_250)]">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Mở menu điều hướng"
          className="text-[oklch(85%_0_0)] hover:text-white transition-colors -ml-1 p-1"
        >
          <Menu className="w-5 h-5" />
        </button>
        <Mic2 className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
        <span className="text-[oklch(95%_0_0)] text-sm font-semibold tracking-tight">
          DoctorCheck AI Call
        </span>
      </header>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <AppSidebar user={user} open={sidebarOpen} onNavigate={() => setSidebarOpen(false)} />

      <main className="md:ml-[220px] min-h-screen bg-[var(--color-surface)] overflow-auto">
        {children}
      </main>
    </div>
  )
}
