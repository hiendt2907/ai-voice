'use client'

import { useState, useEffect } from 'react'
import { Stethoscope, Plus, Trash2 } from 'lucide-react'
import { Field, NumberField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta } from './CloudFoneSection'

interface DoctorCheckSettings {
  baseUrl: string
  apiKey: string
  specialtyMapping: Record<string, string>
  slotMapping: Record<string, string>
  bookingConfirmTemplate: string
  retryCount: number
  timeoutMs: number
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'
type TestStatus = 'idle' | 'testing' | 'ok' | 'error'

const DEFAULT_SLOT_MAPPING: Record<string, string> = {
  specialty: 'service_code',
  patient_name: 'full_name',
  appointment_date: 'date',
  time_of_day: 'time_slot',
}

const DEFAULT_SPECIALTY_MAPPING: Record<string, string> = {
  'nội khoa': 'INTERNAL_MED',
  'nội soi': 'GASTROSCOPY',
  'da liễu': 'DERMATOLOGY',
  'tim mạch': 'CARDIOLOGY',
  'sản phụ khoa': 'OBSTETRICS',
  'nha khoa': 'DENTISTRY',
  'khám tổng quát': 'GENERAL',
}

const DEFAULT_FORM: DoctorCheckSettings = {
  baseUrl: '',
  apiKey: '',
  specialtyMapping: DEFAULT_SPECIALTY_MAPPING,
  slotMapping: DEFAULT_SLOT_MAPPING,
  bookingConfirmTemplate: 'Mã đặt lịch của anh/chị là {{booking_id}} ạ.',
  retryCount: 2,
  timeoutMs: 3000,
  updatedBy: null,
  updatedAt: '',
}

export function DoctorCheckSection() {
  const [form, setForm] = useState<DoctorCheckSettings>(DEFAULT_FORM)
  const [meta, setMeta] = useState<Pick<DoctorCheckSettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testMsg, setTestMsg] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/doctorcheck')
        if (res.ok) {
          const data = (await res.json()) as DoctorCheckSettings
          setForm({ ...DEFAULT_FORM, ...data })
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function set<K extends keyof DoctorCheckSettings>(field: K, value: DoctorCheckSettings[K]) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  function setSpecialtyMapping(mapping: Record<string, string>) {
    setForm((f) => ({ ...f, specialtyMapping: mapping }))
    setSaveStatus('idle')
  }

  function setSlotMapping(mapping: Record<string, string>) {
    setForm((f) => ({ ...f, slotMapping: mapping }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/doctorcheck', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseUrl: form.baseUrl,
          apiKey: form.apiKey,
          specialtyMapping: form.specialtyMapping,
          slotMapping: form.slotMapping,
          bookingConfirmTemplate: form.bookingConfirmTemplate,
          retryCount: form.retryCount,
          timeoutMs: form.timeoutMs,
        }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as DoctorCheckSettings
      setMeta({ updatedBy: saved.updatedBy, updatedAt: saved.updatedAt })
      setSaveStatus('ok')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (e) {
      setErrorMsg((e as Error).message)
      setSaveStatus('error')
    }
  }

  async function handleTest() {
    setTestStatus('testing')
    setTestMsg('')
    try {
      const res = await fetch('/api/v1/settings/doctorcheck/test', { method: 'POST' })
      const data = (await res.json()) as { ok: boolean; message: string }
      setTestStatus(data.ok ? 'ok' : 'error')
      setTestMsg(data.message)
    } catch (e) {
      setTestStatus('error')
      setTestMsg((e as Error).message)
    }
    setTimeout(() => setTestStatus('idle'), 5000)
  }

  if (loading) return <SectionSkeleton />

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.04_145)] flex items-center justify-center">
            <Stethoscope className="w-4 h-4 text-[oklch(42%_0.18_145)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">DoctorCheck API</p>
            <p className="text-xs text-[var(--color-text-muted)]">Tích hợp hệ thống đặt lịch</p>
          </div>
        </div>
        <StatusDot ok={!!form.baseUrl} label={form.baseUrl ? 'Đã cấu hình' : 'Chưa cấu hình'} />
      </div>

      <div className="px-6 py-6 space-y-6">
        {/* Connection */}
        <div className="space-y-4">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Kết nối</p>
          <Field
            label="Base URL"
            hint="Ví dụ: https://api.doctorcheck.vn/v1"
            value={form.baseUrl}
            onChange={(v) => set('baseUrl', v)}
            placeholder="https://api.doctorcheck.vn/v1"
          />
          <Field
            label="API Key"
            hint="Key xác thực từ DoctorCheck team. *** nghĩa là đã cấu hình."
            value={form.apiKey}
            onChange={(v) => set('apiKey', v)}
            type="password"
          />
          <button
            type="button"
            onClick={() => void handleTest()}
            disabled={testStatus === 'testing' || !form.baseUrl}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-surface-overlay)] disabled:opacity-50 transition-colors"
          >
            {testStatus === 'testing' ? 'Đang kiểm tra...' : 'Test kết nối'}
          </button>
          {testMsg && (
            <p className={`text-xs ${testStatus === 'ok' ? 'text-[var(--color-success)]' : 'text-[var(--color-danger)]'}`}>
              {testStatus === 'ok' ? '✓' : '✗'} {testMsg}
            </p>
          )}
        </div>

        {/* Specialty mapping */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Specialty Mapping</p>
          <p className="text-xs text-[var(--color-text-muted)]">Bot nhận → DoctorCheck API code</p>
          <div className="space-y-2">
            {Object.entries(form.specialtyMapping).map(([bot, api]) => (
              <div key={bot} className="flex items-center gap-2">
                <input
                  type="text"
                  value={bot}
                  readOnly
                  className="input flex-1 text-xs bg-[var(--color-surface-overlay)]"
                />
                <span className="text-[var(--color-text-muted)] text-xs">→</span>
                <input
                  type="text"
                  value={api}
                  onChange={(e) => {
                    const next = { ...form.specialtyMapping, [bot]: e.target.value }
                    setSpecialtyMapping(next)
                  }}
                  className="input flex-1 text-xs"
                />
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...form.specialtyMapping }
                    delete next[bot]
                    setSpecialtyMapping(next)
                  }}
                  className="text-[var(--color-text-muted)] hover:text-[var(--color-danger)] transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setSpecialtyMapping({ ...form.specialtyMapping, '': '' })}
            className="inline-flex items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline"
          >
            <Plus className="w-3 h-3" /> Thêm mapping
          </button>
        </div>

        {/* Slot mapping */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Slot Mapping</p>
          <p className="text-xs text-[var(--color-text-muted)]">Script slot name → DoctorCheck API field</p>
          <div className="space-y-2">
            {Object.entries(form.slotMapping).map(([slot, apiField]) => (
              <div key={slot} className="flex items-center gap-2">
                <input
                  type="text"
                  value={slot}
                  readOnly
                  className="input flex-1 text-xs bg-[var(--color-surface-overlay)] font-mono"
                />
                <span className="text-[var(--color-text-muted)] text-xs">→</span>
                <input
                  type="text"
                  value={apiField}
                  onChange={(e) => {
                    const next = { ...form.slotMapping, [slot]: e.target.value }
                    setSlotMapping(next)
                  }}
                  className="input flex-1 text-xs font-mono"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Advanced */}
        <div className="space-y-4">
          <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Cấu hình đặt lịch</p>
          <Field
            label="Thông báo xác nhận"
            hint="Template đọc sau khi đặt lịch thành công. Dùng {{booking_id}} cho mã đặt lịch."
            value={form.bookingConfirmTemplate}
            onChange={(v) => set('bookingConfirmTemplate', v)}
            placeholder="Mã đặt lịch của anh/chị là {{booking_id}} ạ."
          />
          <div className="grid grid-cols-2 gap-4">
            <NumberField
              label="Số lần retry"
              hint="Khi API lỗi (0–5)"
              value={form.retryCount}
              onChange={(v) => set('retryCount', v)}
              min={0}
              max={5}
            />
            <NumberField
              label="Timeout (ms)"
              hint="Thời gian chờ API (1000–30000)"
              value={form.timeoutMs}
              onChange={(v) => set('timeoutMs', v)}
              min={1000}
              max={30000}
              step={500}
            />
          </div>
        </div>

        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} />
    </div>
  )
}
