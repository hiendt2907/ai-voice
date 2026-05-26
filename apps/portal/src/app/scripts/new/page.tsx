'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Loader2 } from 'lucide-react'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">{label}</label>
      {children}
    </div>
  )
}

export default function NewCampaignPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [direction, setDirection] = useState<'inbound' | 'outbound'>('inbound')
  const [voiceProfile, setVoiceProfile] = useState('linh_clone_v1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/scripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, direction, voiceProfile }),
      })
      if (!res.ok) {
        const body = (await res.json()) as { message?: string }
        setError(body.message ?? 'Lỗi tạo campaign')
        return
      }
      const campaign = (await res.json()) as { id: string }
      router.push(`/scripts/${campaign.id}`)
    } catch {
      setError('Không thể kết nối tới server')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-xl mx-auto">
      <Link
        href="/scripts"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Script CMS
      </Link>

      <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight mb-1">
        Tạo Campaign
      </h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-8">
        Campaign là đơn vị quản lý một kịch bản cuộc gọi AI.
      </p>

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-5">
        <Field label="Tên Campaign">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="VD: Booking Inbound — Phòng khám DoctorCheck"
            className="input"
          />
        </Field>

        <Field label="Hướng gọi">
          <div className="flex gap-3">
            {(['inbound', 'outbound'] as const).map((d) => (
              <label
                key={d}
                className={[
                  'flex-1 flex items-center justify-center gap-2 p-3 rounded-lg border text-sm font-medium cursor-pointer transition-all duration-[var(--duration-fast)]',
                  direction === d
                    ? 'border-[var(--color-accent)] bg-[oklch(97%_0.03_250)] text-[var(--color-accent)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[oklch(78%_0.01_250)]',
                ].join(' ')}
              >
                <input
                  type="radio"
                  className="sr-only"
                  name="direction"
                  value={d}
                  checked={direction === d}
                  onChange={() => setDirection(d)}
                />
                {d === 'inbound' ? 'Inbound (gọi vào)' : 'Outbound (gọi ra)'}
              </label>
            ))}
          </div>
        </Field>

        <Field label="Voice Profile">
          <input
            type="text"
            value={voiceProfile}
            onChange={(e) => setVoiceProfile(e.target.value)}
            required
            placeholder="VD: linh_clone_v1"
            className="input"
          />
          <p className="text-xs text-[var(--color-text-muted)] mt-1.5">
            Tên profile giọng TTS đã được đăng ký trong Voice Worker
          </p>
        </Field>

        {error && (
          <div className="rounded-lg bg-[oklch(97%_0.04_27)] border border-[oklch(88%_0.08_27)] text-[oklch(42%_0.2_27)] text-sm px-4 py-3">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <Link
            href="/scripts"
            className="flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg border border-[var(--color-border)] text-sm font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-surface-overlay)] transition-colors"
          >
            Hủy
          </Link>
          <button
            type="submit"
            disabled={loading || !name.trim()}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Tạo Campaign
          </button>
        </div>
      </form>
    </div>
  )
}
