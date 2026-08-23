'use client'

import { useState, useEffect } from 'react'
import { KeyRound, Plus, Copy, Check, AlertCircle, Loader2, ShieldOff } from 'lucide-react'
import { StatusDot, SectionSkeleton, LoadErrorBanner } from './CloudFoneSection'

interface ServiceApiKey {
  id: string
  name: string
  isActive: boolean
  createdAt: string
}

interface CreatedKey extends ServiceApiKey {
  plaintextKey: string
}

export function ServiceApiKeysSection() {
  const [keys, setKeys] = useState<ServiceApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [revokeError, setRevokeError] = useState('')
  // Giá trị plaintext chỉ tồn tại trong state này — không bao giờ được lưu lại
  // vào bất kỳ đâu, và biến mất vĩnh viễn khi rời trang hoặc đóng banner.
  const [justCreated, setJustCreated] = useState<CreatedKey | null>(null)
  const [copied, setCopied] = useState(false)

  async function load() {
    setLoadError('')
    try {
      const res = await fetch('/api/v1/service-api-keys')
      if (!res.ok) {
        setLoadError(`Không thể tải danh sách key (HTTP ${res.status}).`)
        return
      }
      setKeys((await res.json()) as ServiceApiKey[])
    } catch {
      setLoadError('Không thể kết nối máy chủ để tải danh sách key.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleCreate() {
    if (!newName.trim()) return
    setCreating(true)
    setCreateError('')
    try {
      const res = await fetch('/api/v1/service-api-keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim() }),
      })
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const created = (await res.json()) as CreatedKey
      setJustCreated(created)
      setNewName('')
      setCopied(false)
      await load()
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Lỗi tạo key')
    } finally {
      setCreating(false)
    }
  }

  async function handleRevoke(id: string) {
    if (!confirm('Thu hồi key này? Mọi lời gọi service-to-service dùng key này sẽ bị từ chối ngay lập tức.')) return
    setRevokingId(id)
    setRevokeError('')
    try {
      const res = await fetch(`/api/v1/service-api-keys/${id}/revoke`, { method: 'PATCH' })
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      await load()
    } catch (e) {
      setRevokeError(e instanceof Error ? e.message : 'Lỗi thu hồi key')
    } finally {
      setRevokingId(null)
    }
  }

  function copyKey() {
    if (!justCreated) return
    void navigator.clipboard.writeText(justCreated.plaintextKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const activeCount = keys.filter((k) => k.isActive).length

  if (loading) return <SectionSkeleton />

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_290)] flex items-center justify-center">
            <KeyRound className="w-4 h-4 text-[oklch(55%_0.18_290)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">Service API Keys</p>
            <p className="text-xs text-[var(--color-text-muted)]">
              Key xác thực lời gọi nội bộ voice worker ⇄ NestJS (header x-internal-key)
            </p>
          </div>
        </div>
        <StatusDot ok={activeCount > 0} label={`${activeCount} key đang hoạt động`} />
      </div>

      <div className="px-6 py-6 space-y-6">
        <LoadErrorBanner message={loadError} />

        {/* Banner hiển thị key vừa tạo — CHỈ một lần, không thể xem lại */}
        {justCreated && (
          <div className="rounded-xl border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/5 p-4 space-y-3">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-[var(--color-warning)]" />
              <p className="text-sm text-[var(--color-text)]">
                Đây là <strong>lần duy nhất</strong> giá trị này được hiển thị. Sao chép ngay và nạp vào
                cấu hình voice worker (biến <code className="bg-white px-1 rounded">SERVICE_API_KEY</code>) —
                rời trang này thì không xem lại được nữa.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs font-mono bg-white border border-[var(--color-border)] rounded-lg px-3 py-2 overflow-x-auto whitespace-nowrap">
                {justCreated.plaintextKey}
              </code>
              <button
                type="button"
                onClick={copyKey}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm font-medium hover:bg-[var(--color-surface-overlay)] transition-colors shrink-0"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-[var(--color-success)]" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Đã chép' : 'Chép'}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setJustCreated(null)}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
            >
              Tôi đã lưu key này, ẩn banner
            </button>
          </div>
        )}

        {/* Form tạo key mới */}
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Tên key mới</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="vd: voice-worker-2026"
              className="input"
              onKeyDown={(e) => e.key === 'Enter' && void handleCreate()}
            />
          </div>
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={creating || !newName.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors h-[42px]"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Tạo key
          </button>
        </div>
        {createError && (
          <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5" /> {createError}
          </p>
        )}
        {revokeError && (
          <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5" /> {revokeError}
          </p>
        )}

        {/* Danh sách key */}
        <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
          {keys.length === 0 ? (
            <p className="px-4 py-6 text-sm text-center text-[var(--color-text-muted)]">
              Chưa có key nào. Voice worker đang xác thực qua biến môi trường fallback nếu có.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[oklch(97%_0.005_250)] border-b border-[var(--color-border)]">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Tên</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Trạng thái</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Tạo lúc</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {keys.map((k) => (
                  <tr key={k.id} className={k.isActive ? '' : 'opacity-50'}>
                    <td className="px-4 py-3 font-medium text-[var(--color-text)]">{k.name}</td>
                    <td className="px-4 py-3">
                      <span
                        className={[
                          'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border',
                          k.isActive
                            ? 'bg-[oklch(95%_0.06_145)] text-[oklch(38%_0.18_145)] border-[oklch(88%_0.09_145)]'
                            : 'bg-[oklch(96%_0.01_250)] text-[var(--color-text-muted)] border-[var(--color-border)]',
                        ].join(' ')}
                      >
                        {k.isActive ? 'Hoạt động' : 'Đã thu hồi'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-muted)]">
                      {new Date(k.createdAt).toLocaleString('vi-VN')}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {k.isActive && (
                        <button
                          type="button"
                          onClick={() => void handleRevoke(k.id)}
                          disabled={revokingId === k.id}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 disabled:opacity-50 transition-colors"
                        >
                          {revokingId === k.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldOff className="w-3 h-3" />}
                          Thu hồi
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <p className="text-xs text-[var(--color-text-muted)]">
          Bảng rỗng hoàn toàn: hệ thống tự rơi về xác thực bằng biến môi trường
          <code className="bg-[var(--color-surface)] px-1 rounded mx-1">SERVICE_API_KEY</code>
          nếu có cấu hình sẵn (xem InternalAuthGuard).
        </p>
      </div>
    </div>
  )
}
