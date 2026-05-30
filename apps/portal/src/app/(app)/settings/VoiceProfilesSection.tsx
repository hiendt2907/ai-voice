'use client'

import { useState, useEffect, useRef } from 'react'
import { Mic2, ChevronDown, ChevronUp, Play, Plus } from 'lucide-react'
import { Field, SelectField, SliderField, ToggleField } from './Field'

interface VoiceProfile {
  id: string
  displayName: string
  gender: string
  region: string | null
  ttsEngine: string
  elevenlabsVoiceId: string | null
  stabilityFactor: number
  similarityBoost: number
  styleExaggeration: number
  useSpeakerBoost: boolean
  customFillerPool: string[] | null
  isActive: boolean
  createdAt: string
}

interface ProfileForm {
  displayName: string
  gender: string
  region: string
  ttsEngine: string
  elevenlabsVoiceId: string
  stabilityFactor: number
  similarityBoost: number
  styleExaggeration: number
  useSpeakerBoost: boolean
  customFillerPool: string
}

const EMPTY_FORM: ProfileForm = {
  displayName: '',
  gender: 'female',
  region: 'south',
  ttsEngine: 'elevenlabs',
  elevenlabsVoiceId: '',
  stabilityFactor: 0.6,
  similarityBoost: 0.75,
  styleExaggeration: 0.3,
  useSpeakerBoost: true,
  customFillerPool: '',
}

const GENDER_OPTIONS = [
  { value: 'female', label: 'Nữ' },
  { value: 'male', label: 'Nam' },
]

const REGION_OPTIONS = [
  { value: 'south', label: 'Miền Nam' },
  { value: 'north', label: 'Miền Bắc' },
  { value: 'central', label: 'Miền Trung' },
]

const ENGINE_OPTIONS = [
  { value: 'elevenlabs', label: 'ElevenLabs' },
  { value: 'gwen-tts', label: 'gwen-tts (local)' },
]

export function VoiceProfilesSection() {
  const [profiles, setProfiles] = useState<VoiceProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | 'new' | null>(null)
  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [previewLoading, setPreviewLoading] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  async function load() {
    try {
      const res = await fetch('/api/v1/scripts/voice-profiles')
      if (res.ok) setProfiles((await res.json()) as VoiceProfile[])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  function startEdit(profile: VoiceProfile) {
    setEditingId(profile.id)
    setForm({
      displayName: profile.displayName,
      gender: profile.gender,
      region: profile.region ?? 'south',
      ttsEngine: profile.ttsEngine,
      elevenlabsVoiceId: profile.elevenlabsVoiceId ?? '',
      stabilityFactor: profile.stabilityFactor,
      similarityBoost: profile.similarityBoost,
      styleExaggeration: profile.styleExaggeration,
      useSpeakerBoost: profile.useSpeakerBoost,
      customFillerPool: profile.customFillerPool?.join('\n') ?? '',
    })
  }

  function startNew() {
    setEditingId('new')
    setForm(EMPTY_FORM)
  }

  function cancelEdit() {
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  function set<K extends keyof ProfileForm>(field: K, value: ProfileForm[K]) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function handleSave() {
    setSaving(true)
    try {
      const body = {
        ...form,
        customFillerPool: form.customFillerPool
          ? form.customFillerPool.split('\n').map((s) => s.trim()).filter(Boolean)
          : null,
      }
      const url = editingId === 'new'
        ? '/api/v1/scripts/voice-profiles'
        : `/api/v1/scripts/voice-profiles/${editingId}`
      const method = editingId === 'new' ? 'POST' : 'PUT'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        await load()
        cancelEdit()
      }
    } finally {
      setSaving(false)
    }
  }

  async function handlePreview(profileId: string) {
    setPreviewLoading(profileId)
    try {
      const res = await fetch(`/api/v1/scripts/voice-profiles/${profileId}/preview`, { method: 'POST' })
      if (!res.ok) return
      const { audioBase64 } = (await res.json()) as { audioBase64: string }
      const binary = atob(audioBase64)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
      const blob = new Blob([bytes], { type: 'audio/wav' })
      const url = URL.createObjectURL(blob)
      if (audioRef.current) {
        audioRef.current.src = url
        void audioRef.current.play()
      }
    } finally {
      setPreviewLoading(null)
    }
  }

  if (loading) return <div className="animate-pulse h-32 bg-[var(--color-surface-overlay)] rounded-2xl" />

  return (
    <div className="space-y-4">
      <audio ref={audioRef} className="hidden" />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--color-text)]">Voice Profiles</h2>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">Cấu hình giọng cho từng use case</p>
        </div>
        <button
          type="button"
          onClick={startNew}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> Tạo mới
        </button>
      </div>

      {/* New profile form */}
      {editingId === 'new' && (
        <ProfileFormPanel
          form={form}
          set={set}
          onSave={() => void handleSave()}
          onCancel={cancelEdit}
          saving={saving}
        />
      )}

      {/* Profile list */}
      {profiles.length === 0 && editingId !== 'new' && (
        <div className="rounded-xl border border-dashed border-[var(--color-border)] p-8 text-center">
          <Mic2 className="w-6 h-6 text-[var(--color-text-muted)] mx-auto mb-2" />
          <p className="text-sm text-[var(--color-text-muted)]">Chưa có Voice Profile nào</p>
        </div>
      )}

      {profiles.map((profile) => (
        <div key={profile.id} className="rounded-xl border border-[var(--color-border)] bg-white overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-full bg-[oklch(93%_0.06_290)] flex items-center justify-center">
                <Mic2 className="w-3.5 h-3.5 text-[oklch(52%_0.18_290)]" />
              </div>
              <div>
                <p className="text-sm font-semibold text-[var(--color-text)]">{profile.displayName}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {profile.gender === 'female' ? 'Nữ' : 'Nam'} · {profile.ttsEngine} · Stability {profile.stabilityFactor.toFixed(2)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void handlePreview(profile.id)}
                disabled={previewLoading === profile.id}
                title="Nghe thử"
                className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)] transition-colors disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => editingId === profile.id ? cancelEdit() : startEdit(profile)}
                className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)] transition-colors"
              >
                {editingId === profile.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {editingId === profile.id && (
            <div className="border-t border-[var(--color-border)] px-5 py-4">
              <ProfileFormPanel
                form={form}
                set={set}
                onSave={() => void handleSave()}
                onCancel={cancelEdit}
                saving={saving}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function ProfileFormPanel({
  form,
  set,
  onSave,
  onCancel,
  saving,
}: {
  form: ProfileForm
  set: <K extends keyof ProfileForm>(field: K, value: ProfileForm[K]) => void
  onSave: () => void
  onCancel: () => void
  saving: boolean
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] p-5 space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Tên hiển thị"
          value={form.displayName}
          onChange={(v) => set('displayName', v)}
          placeholder="Linh, Minh, ..."
        />
        <SelectField label="Engine" value={form.ttsEngine} onChange={(v) => set('ttsEngine', v)} options={ENGINE_OPTIONS} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <SelectField label="Giới tính" value={form.gender} onChange={(v) => set('gender', v)} options={GENDER_OPTIONS} />
        <SelectField label="Vùng miền" value={form.region} onChange={(v) => set('region', v)} options={REGION_OPTIONS} />
      </div>

      <Field
        label="ElevenLabs Voice ID"
        hint="Vào elevenlabs.io/app/voice-lab → chọn giọng → copy ID"
        value={form.elevenlabsVoiceId}
        onChange={(v) => set('elevenlabsVoiceId', v)}
        placeholder="hpp4J3VqNfWAUOO0d1Us"
      />

      <div className="pt-2 border-t border-[var(--color-border)] space-y-4">
        <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Voice Quality</p>
        <SliderField
          label="Stability"
          hint="0.55–0.65 tự nhiên nhất"
          value={form.stabilityFactor}
          onChange={(v) => set('stabilityFactor', v)}
        />
        <SliderField
          label="Similarity Boost"
          hint="0.70–0.80 cho cuộc gọi"
          value={form.similarityBoost}
          onChange={(v) => set('similarityBoost', v)}
        />
        <SliderField
          label="Style Exaggeration"
          hint="0.25–0.35 cho sự tự nhiên"
          value={form.styleExaggeration}
          onChange={(v) => set('styleExaggeration', v)}
        />
        <ToggleField
          label="Speaker Boost"
          hint="Tăng độ rõ ràng cho điện thoại"
          value={form.useSpeakerBoost}
          onChange={(v) => set('useSpeakerBoost', v)}
        />
      </div>

      <div className="pt-2 border-t border-[var(--color-border)]">
        <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
          Thinking sounds tùy chỉnh
        </label>
        <textarea
          value={form.customFillerPool}
          onChange={(e) => set('customFillerPool', e.target.value)}
          rows={3}
          placeholder={"Dạ, để em kiểm tra lịch nhé...\nVâng, em xem ngay ạ...\n(để trống = dùng mặc định)"}
          className="input w-full text-xs resize-none"
        />
        <p className="text-xs text-[var(--color-text-muted)] mt-1">Mỗi dòng một câu thinking sound</p>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <button type="button" onClick={onCancel} className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--color-border)] hover:bg-white transition-colors">
          Hủy
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving || !form.displayName}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          {saving ? 'Đang lưu...' : 'Lưu'}
        </button>
      </div>
    </div>
  )
}
