'use client'

import { useEffect, useId, useState } from 'react'

export function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
  type = 'text',
  icon,
}: {
  label: string
  hint?: string
  value: string | null | undefined
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  icon?: React.ReactNode
}) {
  const inputId = useId()
  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-[var(--color-text)] mb-1.5">{label}</label>
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">{icon}</span>
        )}
        <input
          id={inputId}
          type={type}
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={['input', icon ? 'pl-8' : ''].join(' ')}
        />
      </div>
      {hint && <p className="text-xs text-[var(--color-text-muted)] mt-1">{hint}</p>}
    </div>
  )
}

export function SelectField({
  label,
  hint,
  value,
  onChange,
  options,
}: {
  label: string
  hint?: string
  value: string | null | undefined
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  const inputId = useId()
  const current = value ?? ''
  // Nếu giá trị hiện tại không nằm trong danh sách option, trình duyệt sẽ tự
  // chọn option đầu tiên trong khi state vẫn giữ giá trị khác — người dùng
  // thấy sai và có thể lưu nhầm. Chèn thêm một option tạm đánh dấu rõ giá trị
  // thật đang được lưu, để <select> luôn hiển thị đúng giá trị của state.
  const hasMatch = current === '' || options.some((o) => o.value === current)
  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-[var(--color-text)] mb-1.5">{label}</label>
      <select
        id={inputId}
        value={current}
        onChange={(e) => onChange(e.target.value)}
        className="input w-full"
      >
        {!hasMatch && (
          <option value={current}>{`⚠️ Giá trị không xác định: ${current}`}</option>
        )}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {hint && <p className="text-xs text-[var(--color-text-muted)] mt-1">{hint}</p>}
    </div>
  )
}

export function SliderField({
  label,
  hint,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.05,
}: {
  label: string
  hint?: string
  value: number | null | undefined
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  const current = value ?? 0
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-sm font-medium text-[var(--color-text)]">{label}</label>
        <span className="text-xs font-mono text-[var(--color-text-muted)]">{current.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={current}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--color-accent)] h-1.5"
      />
      {hint && <p className="text-xs text-[var(--color-text-muted)] mt-1">{hint}</p>}
    </div>
  )
}

export function ToggleField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint?: string
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={[
          'relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors mt-0.5',
          value ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-border)]',
        ].join(' ')}
      >
        <span
          className={[
            'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
            value ? 'translate-x-4' : 'translate-x-0',
          ].join(' ')}
        />
      </button>
      <div>
        <p className="text-sm font-medium text-[var(--color-text)]">{label}</p>
        {hint && <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{hint}</p>}
      </div>
    </div>
  )
}

export function NumberField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string
  hint?: string
  value: number | null | undefined
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  const inputId = useId()
  // Giữ chuỗi hiển thị riêng với giá trị số đã commit ra ngoài: xoá trống ô
  // input không được tự ép về 0 (Number('') === 0) — chỉ khi người dùng gõ
  // một số hợp lệ mới gọi onChange. Đồng bộ lại khi prop value đổi từ bên ngoài.
  const [text, setText] = useState<string>(value == null ? '' : String(value))

  useEffect(() => {
    setText(value == null ? '' : String(value))
  }, [value])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value
    setText(raw)
    if (raw.trim() === '') {
      // Ô trống: chỉ cập nhật hiển thị, không âm thầm ghi giá trị 0 ra ngoài
      return
    }
    const parsed = Number(raw)
    if (!Number.isNaN(parsed)) {
      onChange(parsed)
    }
  }

  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-[var(--color-text)] mb-1.5">{label}</label>
      <input
        id={inputId}
        type="number"
        value={text}
        min={min}
        max={max}
        step={step}
        onChange={handleChange}
        className="input"
      />
      {hint && <p className="text-xs text-[var(--color-text-muted)] mt-1">{hint}</p>}
    </div>
  )
}
