'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

interface Props {
  proposalId: string
  status: 'pending' | 'approved' | 'rejected'
}

export function ProposalActions({ proposalId, status }: Props) {
  const router = useRouter()
  const [loading, setLoading] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function review(decision: 'approved' | 'rejected') {
    setLoading(decision)
    setErrorMsg(null)
    try {
      const res = await fetch(`/api/v1/learning/proposals/${proposalId}/review`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { message?: string }
        throw new Error(body.message ?? `HTTP ${res.status}`)
      }
      router.refresh()
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Không thể kết nối tới server')
    } finally {
      setLoading(null)
    }
  }

  async function apply() {
    setLoading('apply')
    setErrorMsg(null)
    try {
      const res = await fetch(`/api/v1/learning/proposals/${proposalId}/apply`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { message?: string }
        throw new Error(body.message ?? `HTTP ${res.status}`)
      }
      router.refresh()
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Không thể kết nối tới server')
    } finally {
      setLoading(null)
    }
  }

  if (status === 'pending') {
    return (
      <div className="flex flex-col items-end gap-1 shrink-0">
        <div className="flex gap-2">
          <button
            onClick={() => void review('approved')}
            disabled={loading !== null}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border border-[oklch(88%_0.09_145)] hover:opacity-80 disabled:opacity-50 transition-opacity inline-flex items-center gap-1"
          >
            {loading === 'approved' && <Loader2 className="w-3 h-3 animate-spin" />}
            Duyệt
          </button>
          <button
            onClick={() => void review('rejected')}
            disabled={loading !== null}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[oklch(97%_0.04_27)] text-[oklch(42%_0.2_27)] border border-[oklch(88%_0.08_27)] hover:opacity-80 disabled:opacity-50 transition-opacity inline-flex items-center gap-1"
          >
            {loading === 'rejected' && <Loader2 className="w-3 h-3 animate-spin" />}
            Từ chối
          </button>
        </div>
        {errorMsg && (
          <p className="text-xs text-[oklch(42%_0.2_27)] whitespace-nowrap">{errorMsg}</p>
        )}
      </div>
    )
  }

  if (status === 'approved') {
    return (
      <div className="flex flex-col items-end gap-1 shrink-0">
        <button
          onClick={() => void apply()}
          disabled={loading !== null}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[oklch(96%_0.03_250)] text-[oklch(40%_0.16_250)] border border-[oklch(88%_0.06_250)] hover:opacity-80 disabled:opacity-50 transition-opacity inline-flex items-center gap-1"
        >
          {loading === 'apply' && <Loader2 className="w-3 h-3 animate-spin" />}
          Apply to Draft
        </button>
        {errorMsg && (
          <p className="text-xs text-[oklch(42%_0.2_27)] whitespace-nowrap">{errorMsg}</p>
        )}
      </div>
    )
  }

  return null
}
