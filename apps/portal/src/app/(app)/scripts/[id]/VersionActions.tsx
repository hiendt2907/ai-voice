'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Send, Globe, Loader2 } from 'lucide-react'

interface Props {
  campaignId: string
  version: string
  status: 'draft' | 'under_review' | 'published' | 'archived'
}

export function VersionActions({ campaignId, version, status }: Props) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)

  async function call(endpoint: string) {
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/scripts/${campaignId}/versions/${version}/${endpoint}`, {
        method: 'POST',
      })
      if (res.ok) router.refresh()
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-text-muted)]" />

  return (
    <div className="flex items-center gap-1">
      {status === 'draft' && (
        <button
          onClick={() => void call('submit-review')}
          title="Submit for review"
          className="p-1.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:bg-[var(--color-surface-overlay)] transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      )}
      {status === 'under_review' && (
        <button
          onClick={() => void call('publish')}
          title="Publish"
          className="p-1.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-success)] hover:bg-[var(--color-surface-overlay)] transition-colors"
        >
          <Globe className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}
