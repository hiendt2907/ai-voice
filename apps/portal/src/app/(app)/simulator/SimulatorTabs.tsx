'use client'

import { useState } from 'react'
import { MessageSquare, PhoneCall } from 'lucide-react'
import { SimulatorClient } from './SimulatorClient'
import { RealCallPanel } from './RealCallPanel'

interface Campaign {
  id: string
  name: string
  direction: 'inbound' | 'outbound'
  publishedVersionId: string | null
  versions?: { id: string; version: string; body: Record<string, unknown>; status: string }[]
}

export function SimulatorTabs({ campaigns }: { campaigns: Campaign[] }) {
  const [tab, setTab] = useState<'mock' | 'real'>('mock')

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-1 mb-4">
        <button
          onClick={() => setTab('mock')}
          className={[
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            tab === 'mock' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface)]',
          ].join(' ')}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          Giả lập (text)
        </button>
        <button
          onClick={() => setTab('real')}
          className={[
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            tab === 'real' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface)]',
          ].join(' ')}
        >
          <PhoneCall className="w-3.5 h-3.5" />
          Gọi số thật (voip24h)
        </button>
      </div>
      <div className="flex-1 min-h-0">
        {tab === 'mock' ? <SimulatorClient campaigns={campaigns} /> : <RealCallPanel />}
      </div>
    </div>
  )
}
