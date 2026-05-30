'use client'

import { useState, useEffect } from 'react'
import { Server } from 'lucide-react'
import { Field, NumberField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta } from './CloudFoneSection'

interface VoiceWorkerSettings {
  internalUrl: string
  maxConcurrentSessions: number
  sessionCacheTtlSeconds: number
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

export function VoiceWorkerSection() {
  const [form, setForm] = useState<VoiceWorkerSettings>({
    internalUrl: 'http://localhost:8000',
    maxConcurrentSessions: 10,
    sessionCacheTtlSeconds: 3600,
    updatedBy: null,
    updatedAt: '',
  })
  const [meta, setMeta] = useState<Pick<VoiceWorkerSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/voice-worker')
        if (res.ok) {
          const data = (await res.json()) as VoiceWorkerSettings
          setForm(data)
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function set<K extends keyof VoiceWorkerSettings>(field: K, value: VoiceWorkerSettings[K]) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/voice-worker', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          internalUrl: form.internalUrl,
          maxConcurrentSessions: form.maxConcurrentSessions,
          sessionCacheTtlSeconds: form.sessionCacheTtlSeconds,
        }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as VoiceWorkerSettings
      setMeta({ updatedBy: saved.updatedBy, updatedAt: saved.updatedAt })
      setSaveStatus('ok')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (e) {
      setErrorMsg((e as Error).message)
      setSaveStatus('error')
    }
  }

  if (loading) return <SectionSkeleton />

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_200)] flex items-center justify-center">
            <Server className="w-4 h-4 text-[oklch(52%_0.15_200)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">Voice Worker</p>
            <p className="text-xs text-[var(--color-text-muted)]">Kết nối Python voice service</p>
          </div>
        </div>
        <StatusDot ok={!!form.internalUrl} label={form.internalUrl || 'Chưa cấu hình'} />
      </div>

      <div className="px-6 py-6 space-y-5">
        <Field label="Internal URL" hint="URL NestJS dùng để gọi voice worker" value={form.internalUrl} onChange={(v) => set('internalUrl', v)} placeholder="http://localhost:8000" />
        <div className="grid grid-cols-2 gap-4">
          <NumberField label="Max Concurrent Sessions" hint="Số cuộc gọi đồng thời tối đa" value={form.maxConcurrentSessions} onChange={(v) => set('maxConcurrentSessions', v)} min={1} max={100} />
          <NumberField label="Session Cache TTL (giây)" hint="Thời gian cache session trong Redis" value={form.sessionCacheTtlSeconds} onChange={(v) => set('sessionCacheTtlSeconds', v)} min={60} step={60} />
        </div>
        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} />
    </div>
  )
}
