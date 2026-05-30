'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Mic2, Loader2, AlertCircle } from 'lucide-react'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json() as { message?: string }
      if (!res.ok) {
        setError(data.message ?? 'Sai email hoặc mật khẩu')
        return
      }
      router.push('/dashboard')
      router.refresh()
    } catch {
      setError('Không thể kết nối máy chủ')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[oklch(12%_0.025_250)] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-accent)] flex items-center justify-center">
            <Mic2 className="w-5 h-5 text-white" />
          </div>
          <div className="leading-none">
            <p className="text-[oklch(95%_0_0)] text-lg font-semibold tracking-tight">DoctorCheck</p>
            <p className="text-[var(--color-accent)] text-[10px] font-medium uppercase tracking-widest mt-0.5">
              AI Call Portal
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="bg-[oklch(16%_0.03_250)] rounded-2xl border border-[oklch(24%_0.04_250)] p-8">
          <h1 className="text-[oklch(95%_0_0)] text-xl font-semibold mb-1">Đăng nhập</h1>
          <p className="text-[oklch(52%_0.02_250)] text-sm mb-6">
            Vui lòng đăng nhập để tiếp tục
          </p>

          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
            <div>
              <label className="block text-[oklch(75%_0.02_250)] text-xs font-medium mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="admin@doctorcheck.vn"
                className="w-full px-3 py-2.5 rounded-lg border border-[oklch(28%_0.04_250)] bg-[oklch(20%_0.03_250)] text-[oklch(92%_0_0)] placeholder:text-[oklch(38%_0.02_250)] text-sm outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[oklch(55%_0.2_250_/_15%)] transition-colors"
              />
            </div>

            <div>
              <label className="block text-[oklch(75%_0.02_250)] text-xs font-medium mb-1.5">
                Mật khẩu
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
                className="w-full px-3 py-2.5 rounded-lg border border-[oklch(28%_0.04_250)] bg-[oklch(20%_0.03_250)] text-[oklch(92%_0_0)] placeholder:text-[oklch(38%_0.02_250)] text-sm outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[oklch(55%_0.2_250_/_15%)] transition-colors"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-[oklch(20%_0.06_27)] border border-[oklch(30%_0.1_27)]">
                <AlertCircle className="w-4 h-4 text-[var(--color-danger)] shrink-0" />
                <p className="text-[var(--color-danger)] text-xs">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white text-sm font-semibold transition-colors disabled:opacity-50 flex items-center justify-center gap-2 mt-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
            </button>
          </form>
        </div>

        <p className="text-center text-[oklch(32%_0.02_250)] text-xs mt-6">
          DoctorCheck AI Call System · Internal Portal
        </p>
      </div>
    </div>
  )
}
