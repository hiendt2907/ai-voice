'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

type Mode = 'shadow' | 'medium' | 'full'

const MODES: { value: Mode; label: string; hint: string; color: string }[] = [
  {
    value: 'shadow',
    label: 'Shadow',
    hint: 'AI nghe ngầm, không phát âm — chỉ học và ghi log',
    color: 'oklch(52%_0.08_280)',
  },
  {
    value: 'medium',
    label: 'Medium',
    hint: 'AI chỉ trả lời các domain đã chọn, topic khác để người thật xử lý',
    color: 'oklch(52%_0.18_50)',
  },
  {
    value: 'full',
    label: 'Full',
    hint: 'AI trả lời mọi câu hỏi',
    color: 'oklch(38%_0.18_145)',
  },
]

const DOMAIN_OPTIONS = [
  { value: 'booking', label: 'Đặt lịch' },
  { value: 'pricing', label: 'Giá gói khám' },
  { value: 'services', label: 'Dịch vụ' },
  { value: 'hours', label: 'Giờ làm việc' },
  { value: 'insurance', label: 'Bảo hiểm' },
  { value: 'preparation', label: 'Chuẩn bị khám' },
  { value: 'doctors', label: 'Đội ngũ bác sĩ' },
  { value: 'general', label: 'Thông tin chung' },
]

interface Props {
  campaignId: string
  initialMode: Mode
  initialDomains: string[]
}

export function InterceptionModeSelector({ campaignId, initialMode, initialDomains }: Props) {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>(initialMode)
  const [domains, setDomains] = useState<string[]>(initialDomains ?? [])
  const [saving, setSaving] = useState(false)

  function toggleDomain(d: string) {
    setDomains((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d])
  }

  async function save(newMode: Mode, newDomains: string[]) {
    setSaving(true)
    try {
      await fetch(`/api/v1/scripts/${campaignId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interceptionMode: newMode, interceptionDomains: newDomains }),
      })
      router.refresh()
    } finally {
      setSaving(false)
    }
  }

  function selectMode(m: Mode) {
    setMode(m)
    void save(m, domains)
  }

  function saveDomains() {
    void save(mode, domains)
  }

  const current = MODES.find((m) => m.value === mode)!

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {MODES.map((m) => (
          <button
            key={m.value}
            onClick={() => selectMode(m.value)}
            disabled={saving}
            className={[
              'flex-1 py-2 px-3 rounded-lg border text-xs font-semibold transition-all',
              mode === m.value
                ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-white shadow-sm'
                : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)]',
            ].join(' ')}
          >
            {saving && mode === m.value ? (
              <Loader2 className="w-3 h-3 animate-spin mx-auto" />
            ) : m.label}
          </button>
        ))}
      </div>

      <p className="text-xs text-[var(--color-text-muted)]">{current.hint}</p>

      {mode === 'medium' && (
        <div className="pt-2 border-t border-[var(--color-border)]">
          <p className="text-xs font-medium text-[var(--color-text)] mb-2">
            Domain AI can thiệp:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {DOMAIN_OPTIONS.map((d) => (
              <button
                key={d.value}
                onClick={() => toggleDomain(d.value)}
                className={[
                  'px-2.5 py-1 rounded-full text-xs border transition-all',
                  domains.includes(d.value)
                    ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)]',
                ].join(' ')}
              >
                {d.label}
              </button>
            ))}
          </div>
          <button
            onClick={saveDomains}
            disabled={saving}
            className="mt-2 text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
          >
            {saving ? 'Đang lưu…' : 'Lưu domain'}
          </button>
        </div>
      )}
    </div>
  )
}
