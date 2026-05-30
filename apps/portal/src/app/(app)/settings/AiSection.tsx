'use client'

import { useState, useEffect } from 'react'
import { Cpu } from 'lucide-react'
import { Field, NumberField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta } from './CloudFoneSection'

interface AiSettings {
  ollamaBaseUrl: string
  ollamaModel: string
  nluTimeoutMs: number
  responseTimeoutMs: number
  fallbackToSubstring: boolean
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

const DEFAULTS: AiSettings = {
  ollamaBaseUrl: 'http://localhost:11434/v1',
  ollamaModel: 'qwen2.5:latest',
  nluTimeoutMs: 800,
  responseTimeoutMs: 2000,
  fallbackToSubstring: true,
  updatedBy: null,
  updatedAt: '',
}

export function AiSection() {
  const [form, setForm] = useState(DEFAULTS)
  const [meta, setMeta] = useState<Pick<AiSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/ai')
        if (res.ok) {
          const data = (await res.json()) as AiSettings
          setForm(data)
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function set<K extends keyof AiSettings>(field: K, value: AiSettings[K]) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/ai', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ollamaBaseUrl: form.ollamaBaseUrl,
          ollamaModel: form.ollamaModel,
          nluTimeoutMs: form.nluTimeoutMs,
          responseTimeoutMs: form.responseTimeoutMs,
          fallbackToSubstring: form.fallbackToSubstring,
        }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as AiSettings
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
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_140)] flex items-center justify-center">
            <Cpu className="w-4 h-4 text-[oklch(52%_0.18_140)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">AI / LLM</p>
            <p className="text-xs text-[var(--color-text-muted)]">Mô hình ngôn ngữ và nhận diện ý định</p>
          </div>
        </div>
        <StatusDot ok={!!form.ollamaBaseUrl && !!form.ollamaModel} label={form.ollamaModel || 'Chưa cấu hình'} />
      </div>

      <div className="px-6 py-6 space-y-5">
        <Field label="LLM Base URL" hint="OpenAI-compatible endpoint — Ollama: http://localhost:11434/v1 · DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1 · Claude: dùng anthropic SDK riêng" value={form.ollamaBaseUrl} onChange={(v) => set('ollamaBaseUrl', v)} placeholder="http://localhost:11434/v1" />
        <Field label="Model" hint="Tên model ngôn ngữ. Claude Haiku 4.5: nhanh, rẻ, đủ cho slot extraction. Qwen2.5: local, không cần internet" value={form.ollamaModel} onChange={(v) => set('ollamaModel', v)} placeholder="qwen2.5:latest" />
        <div className="grid grid-cols-2 gap-4">
          <NumberField label="NLU Timeout (ms)" hint="Thời gian tối đa chờ LLM phân loại ý định" value={form.nluTimeoutMs} onChange={(v) => set('nluTimeoutMs', v)} min={100} step={100} />
          <NumberField label="Response Timeout (ms)" hint="Thời gian tối đa chờ câu trả lời" value={form.responseTimeoutMs} onChange={(v) => set('responseTimeoutMs', v)} min={100} step={100} />
        </div>
        <div>
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={form.fallbackToSubstring} onChange={(e) => set('fallbackToSubstring', e.target.checked)} className="w-4 h-4 rounded" />
            <span className="text-sm font-medium text-[var(--color-text)]">Fallback sang substring matching khi LLM timeout</span>
          </label>
          <p className="text-xs text-[var(--color-text-muted)] mt-1 ml-7">Đảm bảo cuộc gọi tiếp tục khi AI quá chậm</p>
        </div>
        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} />
    </div>
  )
}
