'use client'

import { useState, useEffect } from 'react'
import { MessageSquare } from 'lucide-react'
import { Field, SelectField, NumberField, SliderField, ToggleField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta, LoadErrorBanner } from './CloudFoneSection'

interface ConversationSettings {
  enabled: boolean
  ollamaModel: string
  systemPrompt: string
  maxHistoryTurns: number
  temperature: number
  sentimentEnabled: boolean
  kbGroundingEnabled: boolean
  sentenceSplitMinChars: number
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

const DEFAULTS: ConversationSettings = {
  enabled: false,
  ollamaModel: 'qwen2.5:3b',
  systemPrompt: '',
  maxHistoryTurns: 5,
  temperature: 0.3,
  sentimentEnabled: false,
  kbGroundingEnabled: true,
  sentenceSplitMinChars: 30,
  updatedBy: null,
  updatedAt: '',
}

const OLLAMA_MODELS = [
  { value: 'qwen2.5:3b', label: 'qwen2.5:3b — ~200ms, tiếng Việt tốt (Khuyến nghị)' },
  { value: 'qwen2.5:7b', label: 'qwen2.5:7b — chất lượng cao hơn, ~400ms' },
  { value: 'qwen2.5:latest', label: 'qwen2.5:latest — auto version mới nhất' },
  { value: 'llama3.2:3b', label: 'llama3.2:3b — Meta, tiếng Việt khá' },
]

export function ConversationSection() {
  const [form, setForm] = useState<ConversationSettings>(DEFAULTS)
  const [meta, setMeta] = useState<Pick<ConversationSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/conversation')
        if (res.ok) {
          const data = (await res.json()) as ConversationSettings
          setForm({ ...DEFAULTS, ...data })
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

  function set<K extends keyof ConversationSettings>(field: K, value: ConversationSettings[K]) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/conversation', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: form.enabled,
          ollamaModel: form.ollamaModel,
          systemPrompt: form.systemPrompt,
          maxHistoryTurns: form.maxHistoryTurns,
          temperature: form.temperature,
          sentimentEnabled: form.sentimentEnabled,
          kbGroundingEnabled: form.kbGroundingEnabled,
          sentenceSplitMinChars: form.sentenceSplitMinChars,
        }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as ConversationSettings
      setMeta({ updatedBy: saved.updatedBy, updatedAt: saved.updatedAt })
      setSaveStatus('ok')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (e) {
      setErrorMsg((e as Error).message)
      setSaveStatus('error')
    }
  }

  if (loading) return <SectionSkeleton />

  const disabled = !form.enabled

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_220)] flex items-center justify-center">
            <MessageSquare className="w-4 h-4 text-[oklch(52%_0.18_220)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">LLM Conversation</p>
            <p className="text-xs text-[var(--color-text-muted)]">Sinh câu trả lời bằng AI thay vì template</p>
          </div>
        </div>
        <StatusDot ok={form.enabled} label={form.enabled ? 'Đang bật' : 'Tắt'} />
      </div>

      <div className="px-6 py-6 space-y-5">
        <LoadErrorBanner message={loadError} />
        <ToggleField
          label="Bật LLM Conversation"
          hint="AI sinh câu trả lời tự nhiên dựa trên KB context. Khi tắt: dùng template trực tiếp từ KB."
          value={form.enabled}
          onChange={(v) => set('enabled', v)}
        />

        <fieldset disabled={disabled} className={disabled ? 'opacity-40 pointer-events-none' : ''}>
          <div className="space-y-5">
            <SelectField
              label="Ollama Model"
              hint="Model cho conversation (khác với NLU model). qwen2.5:3b tối ưu cho tiếng Việt + tốc độ."
              value={form.ollamaModel}
              onChange={(v) => set('ollamaModel', v)}
              options={OLLAMA_MODELS}
            />

            <div>
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
                Persona / System Prompt
              </label>
              <textarea
                value={form.systemPrompt}
                onChange={(e) => set('systemPrompt', e.target.value)}
                placeholder="Bạn là trợ lý tổng đài y tế DoctorCheck. Trả lời ngắn gọn, thân thiện, đúng thông tin từ context. Không bịa thông tin ngoài context."
                rows={5}
                maxLength={4000}
                className="input w-full resize-none font-mono text-xs"
              />
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                {form.systemPrompt.length}/4000 ký tự. Để trống để dùng prompt mặc định.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <NumberField
                label="Context History (turns)"
                hint="Số lượt hội thoại lưu để AI nhớ ngữ cảnh"
                value={form.maxHistoryTurns}
                onChange={(v) => set('maxHistoryTurns', v)}
                min={1}
                max={20}
              />
              <NumberField
                label="Min Chars / Câu TTS"
                hint="Tối thiểu bao nhiêu ký tự mới yield câu cho TTS. Thấp hơn = nhanh hơn nhưng bị ngắt câu nhiều hơn."
                value={form.sentenceSplitMinChars}
                onChange={(v) => set('sentenceSplitMinChars', v)}
                min={10}
                max={200}
              />
            </div>

            <SliderField
              label="Temperature"
              hint="Thấp hơn = trả lời chính xác, nhất quán. 0.3 cho tổng đài y tế."
              value={form.temperature}
              onChange={(v) => set('temperature', v)}
              min={0.0}
              max={1.0}
              step={0.05}
            />

            <div className="pt-2 border-t border-[var(--color-border)]">
              <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">Tính năng nâng cao</p>
              <div className="space-y-4">
                <ToggleField
                  label="Phát hiện cảm xúc khách hàng"
                  hint="Gộp phát hiện emotion vào NLU call. AI điều chỉnh giọng nói (rate, style) theo cảm xúc."
                  value={form.sentimentEnabled}
                  onChange={(v) => set('sentimentEnabled', v)}
                />
                <ToggleField
                  label="Dùng KB làm context (không trả lời thẳng)"
                  hint="KB answer làm grounding fact cho LLM diễn đạt lại. Khi tắt: LLM generate tự do (dễ hallucinate)."
                  value={form.kbGroundingEnabled}
                  onChange={(v) => set('kbGroundingEnabled', v)}
                />
              </div>
            </div>
          </div>
        </fieldset>

        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} saveDisabled={!!loadError} />
    </div>
  )
}
