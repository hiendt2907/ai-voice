import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { AppSidebar } from '@/components/AppSidebar'
import './globals.css'

const inter = Inter({ subsets: ['latin', 'vietnamese'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'DoctorCheck AI Portal',
  description: 'Hệ thống vận hành AI Call — DoctorCheck',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
        <div className="flex min-h-screen">
          <AppSidebar />
          <main className="flex-1 ml-[220px] min-h-screen bg-[var(--color-surface)] overflow-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}
