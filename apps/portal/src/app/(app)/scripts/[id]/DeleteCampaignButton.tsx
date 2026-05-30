'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Trash2, Loader2 } from 'lucide-react'

interface Props {
  campaignId: string
  campaignName: string
}

export function DeleteCampaignButton({ campaignId, campaignName }: Props) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)

  async function handleDelete() {
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/scripts/${campaignId}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) {
        router.push('/scripts')
        router.refresh()
      } else {
        const body = await res.json().catch(() => ({}))
        alert((body as { message?: string })?.message ?? 'Xoá thất bại. Vui lòng thử lại.')
        setOpen(false)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all border-red-200 text-red-600 hover:bg-red-50 hover:border-red-300"
      >
        <Trash2 className="w-3.5 h-3.5" />
        Xoá
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => !loading && setOpen(false)} />
          <div className="relative bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-base font-semibold text-[var(--color-text)] mb-2">
              Xoá campaign này?
            </h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-6">
              Toàn bộ phiên bản script của <strong className="text-[var(--color-text)]">{campaignName}</strong> sẽ bị xoá vĩnh viễn và không thể khôi phục.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setOpen(false)}
                disabled={loading}
                className="px-4 py-2 rounded-lg text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-overlay)] transition-colors disabled:opacity-50"
              >
                Huỷ
              </button>
              <button
                onClick={() => void handleDelete()}
                disabled={loading}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {loading ? 'Đang xoá…' : 'Xoá campaign'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
