'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
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
} from 'lucide-react'

const NAV = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/scripts', label: 'Script CMS', icon: FileText },
  { href: '/calls', label: 'Cuộc gọi', icon: Phone },
  { href: '/qa', label: 'QA Review', icon: Star },
  { href: '/learning', label: 'Learning', icon: Lightbulb },
  { href: '/reports', label: 'Báo cáo', icon: BarChart2 },
  { href: '/audit', label: 'Audit Log', icon: ScrollText },
  { href: '/settings', label: 'Cài đặt', icon: Settings },
]

export function AppSidebar() {
  const pathname = usePathname()

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
        {NAV.map(({ href, label, icon: Icon }) => {
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
                className={['w-4 h-4 shrink-0', active ? 'text-[var(--color-accent)]' : ''].join(
                  ' ',
                )}
              />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[oklch(20%_0.04_250)]">
        <p className="text-[10px] text-[oklch(38%_0.02_250)] leading-relaxed">
          S8 done — CloudFone settings
        </p>
      </div>
    </aside>
  )
}
