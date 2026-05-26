'use client'

import { useState, useEffect } from 'react'
import { Settings2, Save, CheckCircle2, AlertCircle, Loader2, Wifi } from 'lucide-react'

interface CloudFoneSettings {
  odsUrl: string
  apiKey: string
  tenantId: string
  updatedBy: string | null
  updatedAt: string
}

const EMPTY: CloudFoneSettings = { odsUrl: '', apiKey: '', tenantId: '', updatedBy: null, updatedAt: '' }

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

export default function SettingsPage() {
  const [form, setForm] = useState({ odsUrl: '', apiKey: '', tenantId: '' })
  const [meta, setMeta] = useState<Pick<CloudFoneSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/cloudfone')
        if (res.ok) {
          const data = (await res.json()) as CloudFoneSettings
          setForm({ odsUrl: data.odsUrl, apiKey: data.apiKey, tenantId: data.tenantId })
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function set(field: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/cloudfone', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as CloudFoneSettings
      setMeta({ updatedBy: saved.updatedBy, updatedAt: saved.updatedAt })
      setSaveStatus('ok')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (e) {
      setErrorMsg((e as Error).message)
      setSaveStatus('error')
    }
  }

  const isConfigured = form.odsUrl.startsWith('wss://') && form.apiKey.length > 0 && form.tenantId.length > 0

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[300px]">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
      </div>
    )
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Cài đặt</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Cấu hình kết nối tổng đài ảo CloudFone
        </p>
      </div>

      {/* CloudFone section */}
      <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_250)] flex items-center justify-center">
              <Settings2 className="w-4 h-4 text-[var(--color-accent)]" />
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--color-text)]">CloudFone / ODS</p>
              <p className="text-xs text-[var(--color-text-muted)]">Kết nối WebSocket tổng đài ảo</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={[
                'w-2 h-2 rounded-full',
                isConfigured ? 'bg-[var(--color-success)]' : 'bg-[oklch(75%_0.05_250)]',
              ].join(' ')}
            />
            <span className="text-xs text-[var(--color-text-muted)]">
              {isConfigured ? 'Đã cấu hình' : 'Chưa cấu hình'}
            </span>
          </div>
        </div>

        {/* Fields */}
        <div className="px-6 py-6 space-y-5">
          <Field
            label="ODS WebSocket URL"
            hint="wss://ods.cloudfone.vn/ws"
            value={form.odsUrl}
            onChange={(v) => set('odsUrl', v)}
            placeholder="wss://ods.cloudfone.vn/ws"
            icon={<Wifi className="w-3.5 h-3.5" />}
          />
          <Field
            label="API Key"
            hint="API key do CloudFone cấp"
            value={form.apiKey}
            onChange={(v) => set('apiKey', v)}
            placeholder="xxxxxxxxxxxxxxxxxxxxxxxx"
            type="password"
          />
          <Field
            label="Tenant ID"
            hint="Mã tenant / chi nhánh"
            value={form.tenantId}
            onChange={(v) => set('tenantId', v)}
            placeholder="dc"
          />

          {meta?.updatedAt && (
            <p className="text-xs text-[var(--color-text-muted)]">
              Cập nhật lần cuối:{' '}
              {new Date(meta.updatedAt).toLocaleString('vi-VN')}
              {meta.updatedBy && ` bởi ${meta.updatedBy}`}
            </p>
          )}
        </div>

        {/* Footer / Save */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
          <div className="flex items-center gap-2 h-7">
            {saveStatus === 'ok' && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-success)]">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Đã lưu
              </span>
            )}
            {saveStatus === 'error' && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-danger)]">
                <AlertCircle className="w-3.5 h-3.5" />
                {errorMsg}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saveStatus === 'saving'}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
          >
            {saveStatus === 'saving' ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Lưu cài đặt
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
  type = 'text',
  icon,
}: {
  label: string
  hint: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  icon?: React.ReactNode
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
        {label}
      </label>
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
            {icon}
          </span>
        )}
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={['input', icon ? 'pl-8' : ''].join(' ')}
        />
      </div>
      <p className="text-xs text-[var(--color-text-muted)] mt-1">{hint}</p>
    </div>
  )
}
