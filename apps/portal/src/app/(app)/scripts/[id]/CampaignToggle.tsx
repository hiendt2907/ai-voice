'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

interface Props {
  campaignId: string
  isActive: boolean
}

export function CampaignToggle({ campaignId, isActive }: Props) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(isActive)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function toggle() {
    setLoading(true)
    setErrorMsg(null)
    const previousActive = active
    const nextActive = !active
    setActive(nextActive)
    try {
      const res = await fetch(`/api/v1/scripts/${campaignId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isActive: nextActive }),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { message?: string }
        throw new Error(body.message ?? `HTTP ${res.status}`)
      }
      router.refresh()
    } catch (e) {
      setActive(previousActive)
      setErrorMsg(e instanceof Error ? e.message : 'Không thể kết nối tới server')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={() => void toggle()}
        disabled={loading}
        className={[
          'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all',
          active
            ? 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border-[oklch(88%_0.09_145)] hover:opacity-80'
            : 'bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] border-[var(--color-border)] hover:border-[oklch(70%_0.18_145)] hover:text-[oklch(42%_0.18_145)]',
        ].join(' ')}
      >
        {loading ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-[oklch(55%_0.18_145)]' : 'bg-[var(--color-text-muted)]'}`} />
        )}
        {active ? 'Live' : 'Offline'}
      </button>
      {errorMsg && (
        <p className="text-xs text-[oklch(42%_0.2_27)] whitespace-nowrap">{errorMsg}</p>
      )}
    </div>
  )
}
