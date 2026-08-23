'use client'

import { useState, useEffect } from 'react'
import { Mic } from 'lucide-react'
import { SelectField, NumberField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta, LoadErrorBanner } from './CloudFoneSection'

interface SttSettings {
  modelSize: string
  device: string
  computeType: string
  language: string
  endOfUtteranceSilenceMs: number
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

const MODEL_OPTIONS = [
  { value: 'tiny', label: 'tiny — nhanh nhất, độ chính xác thấp' },
  { value: 'small', label: 'small — cân bằng tốc độ / độ chính xác' },
  { value: 'medium', label: 'medium — độ chính xác cao hơn' },
  { value: 'large-v3', label: 'large-v3 — độ chính xác cao nhất, chậm nhất' },
]

const DEVICE_OPTIONS = [
  { value: 'cpu', label: 'CPU' },
  { value: 'cuda', label: 'CUDA (NVIDIA GPU)' },
  { value: 'mps', label: 'MPS (Apple Silicon)' },
]

const COMPUTE_OPTIONS = [
  { value: 'int8', label: 'int8 — nhẹ nhất' },
  { value: 'float16', label: 'float16 — cân bằng' },
  { value: 'float32', label: 'float32 — chính xác nhất' },
]

const LANGUAGE_OPTIONS = [
  { value: 'vi', label: 'vi — Tiếng Việt' },
  { value: 'en', label: 'en — English' },
  { value: 'auto', label: 'auto — Tự động nhận diện' },
]

export function SttSection() {
  const [form, setForm] = useState<SttSettings>({
    modelSize: 'small', device: 'cpu', computeType: 'int8', language: 'vi',
    endOfUtteranceSilenceMs: 400, updatedBy: null, updatedAt: '',
  })
  const [meta, setMeta] = useState<Pick<SttSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/stt')
        if (res.ok) {
          const data = (await res.json()) as SttSettings
          setForm(data)
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        } else {
          // Load thất bại: không cho phép bấm Lưu khi form đang là giá trị mặc định,
          // tránh ghi đè cấu hình thật bằng dữ liệu rỗng/mặc định.
          setLoadError(`Không thể tải cấu hình hiện tại (HTTP ${res.status}). Vui lòng tải lại trang trước khi lưu.`)
        }
      } catch {
        setLoadError('Không thể kết nối máy chủ để tải cấu hình. Vui lòng kiểm tra mạng và tải lại trang trước khi lưu.')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function set<K extends keyof SttSettings>(field: K, value: SttSettings[K]) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/stt', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          modelSize: form.modelSize,
          device: form.device,
          computeType: form.computeType,
          language: form.language ?? 'vi',
          endOfUtteranceSilenceMs: form.endOfUtteranceSilenceMs,
        }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as SttSettings
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
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_30)] flex items-center justify-center">
            <Mic className="w-4 h-4 text-[oklch(55%_0.18_30)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">STT — Nhận dạng giọng nói</p>
            <p className="text-xs text-[var(--color-text-muted)]">Cấu hình faster-whisper</p>
          </div>
        </div>
        <StatusDot ok={true} label={`${form.modelSize} / ${form.device}`} />
      </div>

      <div className="px-6 py-6 space-y-5">
        <LoadErrorBanner message={loadError} />
        <SelectField label="Model Size" hint="Kích thước faster-whisper — small cân bằng tốc độ/chính xác; large-v3 chính xác nhất nhưng cần nhiều RAM" value={form.modelSize} onChange={(v) => set('modelSize', v)} options={MODEL_OPTIONS} />
        <div className="grid grid-cols-2 gap-4">
          <SelectField label="Device" hint="Thiết bị xử lý" value={form.device} onChange={(v) => set('device', v)} options={DEVICE_OPTIONS} />
          <SelectField label="Compute Type" hint="Kiểu dữ liệu tính toán" value={form.computeType} onChange={(v) => set('computeType', v)} options={COMPUTE_OPTIONS} />
        </div>
        <SelectField label="Ngôn ngữ nhận dạng" hint="Mặc định vi (tiếng Việt). ElevenLabs Scribe hỗ trợ tự động nhận diện (auto). Chọn đúng ngôn ngữ giúp tăng độ chính xác đáng kể" value={form.language ?? 'vi'} onChange={(v) => set('language', v)} options={LANGUAGE_OPTIONS} />
        <NumberField label="Silence Timeout (ms)" hint="Khoảng im lặng để kết thúc lượt nói" value={form.endOfUtteranceSilenceMs} onChange={(v) => set('endOfUtteranceSilenceMs', v)} min={100} max={2000} step={50} />
        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} saveDisabled={!!loadError} />
    </div>
  )
}
