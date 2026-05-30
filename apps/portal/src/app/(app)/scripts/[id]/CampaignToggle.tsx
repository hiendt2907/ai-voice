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

  async function toggle() {
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/scripts/${campaignId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isActive: !active }),
      })
      if (res.ok) {
        setActive(!active)
        router.refresh()
      }
    } finally {
      setLoading(false)
    }
  }

  return (
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
  )
}
