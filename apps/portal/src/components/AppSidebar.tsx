'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  LayoutDashboard,
  FileText,
  Phone,
  Star,
  Lightbulb,
  BarChart2,
  ScrollText,
  Settings,
  Mic2,
  LogOut,
  Cpu,
  BookOpen,
  Zap,
  HelpCircle,
} from 'lucide-react'

type NavItem = {
  href: string
  label: string
  icon: React.ElementType
  /** Roles that can see this item. Undefined = all roles. */
  roles?: string[]
}

const NAV: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/scripts', label: 'Script CMS', icon: FileText, roles: ['admin', 'operator'] },
  { href: '/knowledge', label: 'Knowledge Base', icon: BookOpen, roles: ['admin', 'operator'] },
  { href: '/nlu', label: 'NLU Content', icon: Zap, roles: ['admin', 'operator'] },
  { href: '/calls', label: 'Cuộc gọi', icon: Phone, roles: ['admin', 'operator', 'qa'] },
  { href: '/qa', label: 'QA Review', icon: Star, roles: ['admin', 'qa'] },
  { href: '/learning', label: 'Learning', icon: Lightbulb, roles: ['admin', 'qa'] },
  { href: '/reports', label: 'Báo cáo', icon: BarChart2 },
  { href: '/audit', label: 'Audit Log', icon: ScrollText, roles: ['admin'] },
  { href: '/simulator', label: 'Simulator', icon: Cpu, roles: ['admin', 'operator'] },
  { href: '/settings', label: 'Cài đặt', icon: Settings, roles: ['admin'] },
]

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  operator: 'Operator',
  qa: 'QA',
  viewer: 'Viewer',
}

interface User {
  email: string
  role: string
}

interface AppSidebarProps {
  user: User | null
}

export function AppSidebar({ user }: AppSidebarProps) {
  const pathname = usePathname()
  const router = useRouter()
  const userRole = user?.role ?? 'viewer'

  const visibleNav = NAV.filter(
    (item) => !item.roles || item.roles.includes(userRole),
  )

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' })
    router.push('/login')
    router.refresh()
  }

  return (
    <aside className="fixed inset-y-0 left-0 w-[220px] flex flex-col bg-[oklch(12%_0.025_250)] border-r border-[oklch(20%_0.04_250)] z-40">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-[oklch(20%_0.04_250)]">
        <Mic2 className="w-5 h-5 text-[var(--color-accent)] shrink-0" />
        <div className="flex flex-col leading-none">
          <span className="text-[oklch(95%_0_0)] text-sm font-semibold tracking-tight">
            DoctorCheck
          </span>
          <span className="text-[var(--color-accent)] text-[10px] font-medium uppercase tracking-widest mt-0.5">
            AI Call
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2.5 space-y-0.5 overflow-y-auto">
        {visibleNav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/dashboard' && pathname.startsWith(href))
          return (
            <Link
              key={href}
              href={href}
              className={[
                'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-[var(--duration-fast)]',
                active
                  ? 'bg-[oklch(22%_0.08_250)] text-[oklch(95%_0_0)]'
                  : 'text-[oklch(58%_0.02_250)] hover:bg-[oklch(18%_0.04_250)] hover:text-[oklch(85%_0_0)]',
              ].join(' ')}
            >
              <Icon
                className={['w-4 h-4 shrink-0', active ? 'text-[var(--color-accent)]' : ''].join(' ')}
              />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Help / Guide — separated from main nav */}
      <div className="px-2.5 py-2.5 border-t border-[oklch(20%_0.04_250)]">
        {(() => {
          const active = pathname === '/guide' || pathname.startsWith('/guide')
          return (
            <Link
              href="/guide"
              className={[
                'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-[var(--duration-fast)]',
                active
                  ? 'bg-[oklch(22%_0.08_250)] text-[oklch(95%_0_0)]'
                  : 'text-[oklch(58%_0.02_250)] hover:bg-[oklch(18%_0.04_250)] hover:text-[oklch(85%_0_0)]',
              ].join(' ')}
            >
              <HelpCircle
                className={['w-4 h-4 shrink-0', active ? 'text-[var(--color-accent)]' : ''].join(' ')}
              />
              Hướng dẫn sử dụng
            </Link>
          )
        })()}
      </div>

      {/* User menu */}
      <div className="px-3 py-3 border-t border-[oklch(20%_0.04_250)]">
        {user ? (
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg">
            <div className="w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center text-white text-xs font-bold shrink-0">
              {user.email[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[oklch(85%_0_0)] text-xs font-medium truncate">{user.email}</p>
              <p className="text-[oklch(42%_0.02_250)] text-[10px]">
                {ROLE_LABELS[user.role] ?? user.role}
              </p>
            </div>
            <button
              onClick={() => void handleLogout()}
              title="Đăng xuất"
              className="text-[oklch(38%_0.02_250)] hover:text-[var(--color-danger)] transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <p className="text-[10px] text-[oklch(32%_0.02_250)] px-2 py-1">
            Không xác thực
          </p>
        )}
      </div>
    </aside>
  )
}
