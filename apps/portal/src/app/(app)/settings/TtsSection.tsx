'use client'

import { useState, useEffect, useCallback } from 'react'
import { Volume2, Eye, EyeOff, RefreshCw } from 'lucide-react'
import { Field, SelectField, NumberField, SliderField, ToggleField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta } from './CloudFoneSection'

interface TtsSettings {
  engine: string
  voice: string
  sampleRate: number
  speedFactor: number
  elevenlabsApiKey: string
  elevenlabsVoiceId: string
  elevenlabsModelId: string
  elevenlabsStability: number
  elevenlabsSimilarityBoost: number
  elevenlabsStyleExaggeration: number
  elevenlabsUseSpeakerBoost: boolean
  engineFallbackOrder: string[]
  elevenlabsDailyCharQuota: number
  circuitBreakerFailures: number
  circuitBreakerResetSecs: number
  updatedBy: string | null
  updatedAt: string
}

interface TtsHealth {
  engines: Record<string, 'closed' | 'open' | 'half-open'>
  quota: { used: number; cap: number; remaining: number; date: string }
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

const ENGINE_OPTIONS = [
  { value: 'elevenlabs', label: 'ElevenLabs — cloud, tiếng Việt chất lượng cao' },
  { value: 'edge-tts', label: 'edge-tts — cloud, miễn phí' },
  { value: 'gwen-tts', label: 'gwen-tts — Qwen3 finetuned tiếng Việt (local)' },
  { value: 'kokoro', label: 'kokoro — local, offline' },
]

const ELEVENLABS_MODELS = [
  { value: 'eleven_turbo_v2_5', label: 'Turbo v2.5 — ~600ms TTFA (Khuyến nghị)' },
  { value: 'eleven_flash_v2_5', label: 'Flash v2.5 — ~330ms TTFA (Nhanh nhất)' },
  { value: 'eleven_multilingual_v2', label: 'Multilingual v2 — Chất lượng cao, ~1.5s' },
  { value: 'eleven_v3', label: 'v3 — Legacy, chậm (~2.3s)' },
]

const EDGE_TTS_VOICES = [
  { value: 'vi-VN-HoaiMyNeural', label: 'HoaiMy — nữ (mặc định)' },
  { value: 'vi-VN-NamMinhNeural', label: 'NamMinh — nam' },
]

const GWEN_VOICES = [
  { value: 'reference', label: 'Reference voice (samples/voice/reference.wav)' },
]

const KOKORO_VOICES = [
  { value: 'af_heart', label: 'af_heart (English)' },
]

function getVoiceOptions(engine: string) {
  if (engine === 'edge-tts') return EDGE_TTS_VOICES
  if (engine === 'gwen-tts') return GWEN_VOICES
  return KOKORO_VOICES
}

const ENGINE_NAMES: Record<string, string> = {
  elevenlabs: 'ElevenLabs',
  'edge-tts': 'edge-tts',
  local: 'Local',
}

const CIRCUIT_DOT_COLOR: Record<string, string> = {
  closed: 'bg-emerald-500',
  'half-open': 'bg-amber-400',
  open: 'bg-red-500',
}

const DEFAULT_FORM: TtsSettings = {
  engine: 'elevenlabs',
  voice: 'vi-VN-HoaiMyNeural',
  sampleRate: 8000,
  speedFactor: 1.0,
  elevenlabsApiKey: '',
  elevenlabsVoiceId: 'hpp4J3VqNfWAUOO0d1Us',
  elevenlabsModelId: 'eleven_turbo_v2_5',
  elevenlabsStability: 0.6,
  elevenlabsSimilarityBoost: 0.75,
  elevenlabsStyleExaggeration: 0.3,
  elevenlabsUseSpeakerBoost: true,
  engineFallbackOrder: ['elevenlabs', 'edge-tts', 'local'],
  elevenlabsDailyCharQuota: 0,
  circuitBreakerFailures: 3,
  circuitBreakerResetSecs: 300,
  updatedBy: null,
  updatedAt: '',
}

export function TtsSection() {
  const [form, setForm] = useState<TtsSettings>(DEFAULT_FORM)
  const [meta, setMeta] = useState<Pick<TtsSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [hasExistingKey, setHasExistingKey] = useState(false)
  const [health, setHealth] = useState<TtsHealth | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/tts')
        if (res.ok) {
          const data = (await res.json()) as TtsSettings
          setHasExistingKey(data.elevenlabsApiKey === '***')
          setForm({ ...DEFAULT_FORM, ...data, elevenlabsApiKey: '' })
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const refreshHealth = useCallback(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/tts/health')
        if (res.ok) setHealth((await res.json()) as TtsHealth)
      } catch {
        // non-fatal
      }
    })()
  }, [])

  useEffect(() => {
    refreshHealth()
    const timer = setInterval(refreshHealth, 30_000)
    return () => clearInterval(timer)
  }, [refreshHealth])

  function set<K extends keyof TtsSettings>(field: K, value: TtsSettings[K]) {
    setForm((f) => {
      const next = { ...f, [field]: value }
      if (field === 'engine' && value !== 'elevenlabs') {
        const opts = getVoiceOptions(value as string)
        next.voice = opts[0]?.value ?? ''
      }
      return next
    })
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const body: Record<string, unknown> = {
        engine: form.engine,
        voice: form.voice,
        sampleRate: form.sampleRate,
        speedFactor: form.speedFactor,
        elevenlabsApiKey: form.elevenlabsApiKey.trim() === '' ? '***' : form.elevenlabsApiKey,
        elevenlabsVoiceId: form.elevenlabsVoiceId,
        elevenlabsModelId: form.elevenlabsModelId,
        elevenlabsStability: form.elevenlabsStability,
        elevenlabsSimilarityBoost: form.elevenlabsSimilarityBoost,
        elevenlabsStyleExaggeration: form.elevenlabsStyleExaggeration,
        elevenlabsUseSpeakerBoost: form.elevenlabsUseSpeakerBoost,
        engineFallbackOrder: form.engineFallbackOrder,
        elevenlabsDailyCharQuota: form.elevenlabsDailyCharQuota,
        circuitBreakerFailures: form.circuitBreakerFailures,
        circuitBreakerResetSecs: form.circuitBreakerResetSecs,
      }
      const res = await fetch('/api/v1/settings/tts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as TtsSettings
      setForm((f) => ({ ...f, elevenlabsApiKey: saved.elevenlabsApiKey }))
      setMeta({ updatedBy: saved.updatedBy, updatedAt: saved.updatedAt })
      setSaveStatus('ok')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (e) {
      setErrorMsg((e as Error).message)
      setSaveStatus('error')
    }
  }

  if (loading) return <SectionSkeleton />

  const isElevenLabs = form.engine === 'elevenlabs'

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_290)] flex items-center justify-center">
            <Volume2 className="w-4 h-4 text-[oklch(52%_0.18_290)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">TTS — Tổng hợp giọng nói</p>
            <p className="text-xs text-[var(--color-text-muted)]">Engine và giọng đọc</p>
          </div>
        </div>
        <StatusDot ok={true} label={form.engine} />
      </div>

      <div className="px-6 py-6 space-y-5">
        <SelectField
          label="Engine"
          hint="ElevenLabs cho chất lượng tiếng Việt tốt nhất"
          value={form.engine}
          onChange={(v) => set('engine', v)}
          options={ENGINE_OPTIONS}
        />

        {isElevenLabs ? (
          <>
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-medium text-[var(--color-text)]">API Key</label>
                {hasExistingKey && form.elevenlabsApiKey === '' && (
                  <span className="text-xs text-emerald-600 font-medium">✓ Đã cấu hình — để trống để giữ nguyên</span>
                )}
              </div>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={form.elevenlabsApiKey}
                  onChange={(e) => set('elevenlabsApiKey', e.target.value)}
                  placeholder={hasExistingKey ? 'Nhập key mới để thay thế…' : 'sk_...'}
                  className="input pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                Lấy tại elevenlabs.io → Profile → API Keys.
              </p>
            </div>

            <Field
              label="Voice ID"
              hint="ID giọng trên ElevenLabs. Vào elevenlabs.io/app/voice-lab → chọn giọng → copy ID bên dưới tên giọng"
              value={form.elevenlabsVoiceId}
              onChange={(v) => set('elevenlabsVoiceId', v)}
              placeholder="hpp4J3VqNfWAUOO0d1Us"
            />

            <SelectField
              label="Model"
              hint="Turbo v2.5 (~600ms) hoặc Flash v2.5 (~330ms) cho thoại thời gian thực. Multilingual v2 chất lượng cao hơn nhưng chậm hơn (~1.5s)."
              value={form.elevenlabsModelId}
              onChange={(v) => set('elevenlabsModelId', v)}
              options={ELEVENLABS_MODELS}
            />

            <div className="pt-2 border-t border-[var(--color-border)]">
              <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">Chất lượng giọng</p>
              <div className="space-y-5">
                <SliderField
                  label="Stability"
                  hint="Thấp hơn = tự nhiên hơn, ít robot. 0.55–0.65 tốt nhất cho thoại"
                  value={form.elevenlabsStability}
                  onChange={(v) => set('elevenlabsStability', v)}
                />
                <SliderField
                  label="Similarity Boost"
                  hint="Độ trung thực với giọng gốc. 0.70–0.80 cho cuộc gọi"
                  value={form.elevenlabsSimilarityBoost}
                  onChange={(v) => set('elevenlabsSimilarityBoost', v)}
                />
                <SliderField
                  label="Style Exaggeration"
                  hint="Mức độ phong cách. 0.25–0.35 cho sự tự nhiên"
                  value={form.elevenlabsStyleExaggeration}
                  onChange={(v) => set('elevenlabsStyleExaggeration', v)}
                />
                <ToggleField
                  label="Speaker Boost"
                  hint="Tăng độ rõ ràng của giọng. Bật cho điện thoại"
                  value={form.elevenlabsUseSpeakerBoost}
                  onChange={(v) => set('elevenlabsUseSpeakerBoost', v)}
                />
              </div>
            </div>
          </>
        ) : (
          <>
            <SelectField
              label="Giọng đọc"
              hint="Danh sách thay đổi theo engine"
              value={form.voice}
              onChange={(v) => set('voice', v)}
              options={getVoiceOptions(form.engine)}
            />
            <div className="grid grid-cols-2 gap-4">
              <NumberField
                label="Sample Rate (Hz)"
                hint="8000 Hz cho điện thoại"
                value={form.sampleRate}
                onChange={(v) => set('sampleRate', v)}
                min={8000}
                max={44100}
                step={8000}
              />
              <NumberField
                label="Speed Factor"
                hint="0.8 – 1.2, mặc định 1.0"
                value={form.speedFactor}
                onChange={(v) => set('speedFactor', v)}
                min={0.5}
                max={2.0}
                step={0.1}
              />
            </div>
          </>
        )}

        <div className="pt-2 border-t border-[var(--color-border)]">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">Thứ tự dự phòng</p>
          <div className="space-y-3">
            {(['0', '1', '2'] as const).map((idx) => (
              <div key={idx} className="flex items-center gap-3">
                <span className="text-xs text-[var(--color-text-muted)] w-16 shrink-0">
                  {idx === '0' ? 'Primary' : idx === '1' ? 'Fallback 1' : 'Fallback 2'}
                </span>
                <select
                  value={form.engineFallbackOrder[Number(idx)] ?? ''}
                  onChange={(e) => {
                    const next = [...form.engineFallbackOrder]
                    next[Number(idx)] = e.target.value
                    set('engineFallbackOrder', next)
                  }}
                  className="input flex-1"
                >
                  <option value="elevenlabs">ElevenLabs</option>
                  <option value="edge-tts">edge-tts</option>
                  <option value="local">Local / gwen-tts</option>
                </select>
              </div>
            ))}
          </div>
        </div>

        <div className="pt-2 border-t border-[var(--color-border)]">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">ElevenLabs Quota</p>
          <NumberField
            label="Daily Char Quota"
            hint="Giới hạn ký tự/ngày. 0 = không giới hạn. Dùng để tránh vượt quota khi nhiều cuộc gọi."
            value={form.elevenlabsDailyCharQuota}
            onChange={(v) => set('elevenlabsDailyCharQuota', v)}
            min={0}
            step={10000}
          />
        </div>

        <div className="pt-2 border-t border-[var(--color-border)]">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mb-4">Circuit Breaker</p>
          <div className="grid grid-cols-2 gap-4">
            <NumberField
              label="Ngưỡng lỗi mở circuit"
              hint="Số lần thất bại liên tiếp để tạm dừng engine"
              value={form.circuitBreakerFailures}
              onChange={(v) => set('circuitBreakerFailures', v)}
              min={1}
              max={20}
            />
            <NumberField
              label="Reset sau (giây)"
              hint="Thời gian chờ trước khi thử lại engine bị lỗi"
              value={form.circuitBreakerResetSecs}
              onChange={(v) => set('circuitBreakerResetSecs', v)}
              min={30}
              step={30}
            />
          </div>
        </div>

        {health && (
          <div className="pt-2 border-t border-[var(--color-border)]">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Trạng thái Engine</p>
              <button
                type="button"
                onClick={refreshHealth}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
                title="Refresh"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="space-y-2">
              {Object.entries(health.engines).map(([name, status]) => (
                <div key={name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className={['w-2 h-2 rounded-full', CIRCUIT_DOT_COLOR[status] ?? 'bg-gray-400'].join(' ')} />
                    <span className="font-medium text-[var(--color-text)]">{ENGINE_NAMES[name] ?? name}</span>
                  </div>
                  <span className="text-[var(--color-text-muted)] capitalize">{status}</span>
                </div>
              ))}
              {health.quota.cap > 0 && (
                <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="text-[var(--color-text-muted)]">ElevenLabs quota {health.quota.date}</span>
                    <span className="font-mono text-[var(--color-text)]">
                      {health.quota.used.toLocaleString()} / {health.quota.cap.toLocaleString()} chars
                    </span>
                  </div>
                  <div className="w-full bg-[var(--color-surface-overlay)] rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-[var(--color-accent)] transition-all"
                      style={{ width: `${Math.min(100, (health.quota.used / health.quota.cap) * 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} />
    </div>
  )
}
