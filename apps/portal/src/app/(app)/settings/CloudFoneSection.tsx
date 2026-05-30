'use client'

import { useState, useEffect } from 'react'
import { Settings2, Save, CheckCircle2, AlertCircle, Loader2, Wifi, Zap } from 'lucide-react'
import { Field } from './Field'

interface CloudFoneSettings {
  odsUrl: string
  apiKey: string
  tenantId: string
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'
type TestStatus = 'idle' | 'testing' | 'ok' | 'error'

export function CloudFoneSection() {
  const [form, setForm] = useState({ odsUrl: '', apiKey: '', tenantId: '' })
  const [meta, setMeta] = useState<Pick<CloudFoneSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testMsg, setTestMsg] = useState('')

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

  async function handleTest() {
    setTestStatus('testing')
    setTestMsg('')
    try {
      const res = await fetch('/api/v1/settings/cloudfone/test', { method: 'POST' })
      const data = (await res.json()) as { ok: boolean; message: string }
      setTestStatus(data.ok ? 'ok' : 'error')
      setTestMsg(data.message)
      setTimeout(() => setTestStatus('idle'), 5000)
    } catch {
      setTestStatus('error')
      setTestMsg('Không thể kết nối máy chủ')
    }
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

  if (loading) return <SectionSkeleton />

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
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
        <StatusDot ok={isConfigured} label={isConfigured ? 'Đã cấu hình' : 'Chưa cấu hình'} />
      </div>

      <div className="px-6 py-6 space-y-5">
        <Field label="ODS WebSocket URL" hint="Format: wss://ods.cloudfone.vn/ws — URL do CloudFone cung cấp, bắt đầu bằng wss://" value={form.odsUrl} onChange={(v) => set('odsUrl', v)} placeholder="wss://ods.cloudfone.vn/ws" icon={<Wifi className="w-3.5 h-3.5" />} />
        <Field label="API Key" hint="Service key để xác thực với ODS gateway — lấy trong trang quản trị CloudFone" value={form.apiKey} onChange={(v) => set('apiKey', v)} placeholder="xxxxxxxxxxxxxxxxxxxxxxxx" type="password" />
        <Field label="Tenant ID" hint="Mã tenant / chi nhánh — thường là ký tự ngắn như 'dc' hoặc 'doctorcheck'" value={form.tenantId} onChange={(v) => set('tenantId', v)} placeholder="dc" />
        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter
        saveStatus={saveStatus} errorMsg={errorMsg}
        testStatus={testStatus} testMsg={testMsg}
        onTest={() => void handleTest()} onSave={() => void handleSave()}
      />
    </div>
  )
}

// ── Shared sub-components ────────────────────────────────────────────────────

export function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={['w-2 h-2 rounded-full', ok ? 'bg-[var(--color-success)]' : 'bg-[oklch(75%_0.05_250)]'].join(' ')} />
      <span className="text-xs text-[var(--color-text-muted)]">{label}</span>
    </div>
  )
}

export function Meta({ updatedAt, updatedBy }: { updatedAt?: string | null; updatedBy?: string | null }) {
  if (!updatedAt) return null
  return (
    <p className="text-xs text-[var(--color-text-muted)]">
      Cập nhật lần cuối: {new Date(updatedAt).toLocaleString('vi-VN')}
      {updatedBy && ` bởi ${updatedBy}`}
    </p>
  )
}

export function SectionFooter({
  saveStatus, errorMsg, testStatus, testMsg, onTest, onSave,
}: {
  saveStatus: SaveStatus; errorMsg: string
  testStatus?: TestStatus; testMsg?: string
  onTest?: () => void; onSave: () => void
}) {
  return (
    <div className="flex items-center justify-between px-6 py-4 border-t border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
      <div className="flex items-center gap-3 h-7">
        {saveStatus === 'ok' && <Feedback icon={<CheckCircle2 className="w-3.5 h-3.5" />} text="Đã lưu" color="success" />}
        {saveStatus === 'error' && <Feedback icon={<AlertCircle className="w-3.5 h-3.5" />} text={errorMsg} color="danger" />}
        {testStatus === 'ok' && testMsg && <Feedback icon={<CheckCircle2 className="w-3.5 h-3.5" />} text={testMsg} color="success" />}
        {testStatus === 'error' && testMsg && <Feedback icon={<AlertCircle className="w-3.5 h-3.5" />} text={testMsg} color="danger" />}
      </div>
      <div className="flex items-center gap-2">
        {onTest && (
          <button type="button" onClick={onTest} disabled={testStatus === 'testing'} className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] text-sm font-medium hover:bg-[var(--color-surface-overlay)] disabled:opacity-50 transition-colors">
            {testStatus === 'testing' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Test kết nối
          </button>
        )}
        <button type="button" onClick={onSave} disabled={saveStatus === 'saving'} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors">
          {saveStatus === 'saving' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Lưu cài đặt
        </button>
      </div>
    </div>
  )
}

function Feedback({ icon, text, color }: { icon: React.ReactNode; text: string; color: 'success' | 'danger' }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-${color})]`}>
      {icon}{text}
    </span>
  )
}

export function SectionSkeleton() {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="h-4 w-32 bg-[var(--color-border)] rounded animate-pulse" />
      </div>
      <div className="px-6 py-6 space-y-5">
        {[1, 2, 3].map((i) => (
          <div key={i} className="space-y-1.5">
            <div className="h-3 w-24 bg-[var(--color-border)] rounded animate-pulse" />
            <div className="h-9 w-full bg-[var(--color-border)] rounded-lg animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  )
}
