'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Plus, X, HelpCircle } from 'lucide-react'
import { KB_CATEGORIES, CATEGORY_LABELS } from '@/lib/api/knowledge'
import type { CreateArticlePayload, UpdateArticlePayload } from '@/lib/api/knowledge'

interface ArticleFormProps {
  initialData?: {
    title: string
    category: string | null
    tags: string[]
    questionVariants: string[]
    answerText: string
    answerMale: string | null
    answerFemale: string | null
    confidenceThreshold: number
    isActive?: boolean
  }
  onSubmit: (data: CreateArticlePayload | UpdateArticlePayload) => Promise<void>
  submitLabel?: string
}

export function ArticleForm({ initialData, onSubmit, submitLabel = 'Lưu' }: ArticleFormProps) {
  const router = useRouter()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [title, setTitle] = useState(initialData?.title ?? '')
  const [category, setCategory] = useState(initialData?.category ?? '')
  const [tags, setTags] = useState<string[]>(initialData?.tags ?? [])
  const [tagInput, setTagInput] = useState('')
  const [questionVariants, setQuestionVariants] = useState<string[]>(
    initialData?.questionVariants?.length ? initialData.questionVariants : [''],
  )
  const [answerText, setAnswerText] = useState(initialData?.answerText ?? '')
  const [answerMale, setAnswerMale] = useState(initialData?.answerMale ?? '')
  const [answerFemale, setAnswerFemale] = useState(initialData?.answerFemale ?? '')
  const [confidenceThreshold, setConfidenceThreshold] = useState(
    initialData?.confidenceThreshold ?? 0.82,
  )
  const [isActive, setIsActive] = useState(initialData?.isActive ?? true)

  function addVariant() {
    setQuestionVariants((prev) => [...prev, ''])
  }

  function removeVariant(idx: number) {
    setQuestionVariants((prev) => prev.filter((_, i) => i !== idx))
  }

  function updateVariant(idx: number, value: string) {
    setQuestionVariants((prev) => prev.map((v, i) => (i === idx ? value : v)))
  }

  function addTag() {
    const t = tagInput.trim()
    if (t && !tags.includes(t)) setTags((prev) => [...prev, t])
    setTagInput('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const variants = questionVariants.filter((v) => v.trim())
    if (!title.trim()) return setError('Tiêu đề không được để trống')
    if (!variants.length) return setError('Cần ít nhất 1 câu hỏi mẫu')
    if (!answerText.trim()) return setError('Câu trả lời không được để trống')

    setSaving(true)
    setError(null)
    try {
      await onSubmit({
        title: title.trim(),
        category: category || undefined,
        tags,
        questionVariants: variants,
        answerText: answerText.trim(),
        answerMale: answerMale.trim() || undefined,
        answerFemale: answerFemale.trim() || undefined,
        confidenceThreshold,
        ...(initialData !== undefined ? { isActive } : {}),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-8">
      {/* Basic info */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-[var(--color-text)] uppercase tracking-wide">
          Thông tin cơ bản
        </h2>

        <Field label="Tiêu đề" required>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ví dụ: Giờ mở cửa phòng khám"
            className={inputCls}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Danh mục">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className={inputCls}
            >
              <option value="">-- Chọn danh mục --</option>
              {KB_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABELS[c]}
                </option>
              ))}
            </select>
          </Field>

          <Field label={`Độ tin cậy tối thiểu: ${confidenceThreshold.toFixed(2)}`}>
            <input
              type="range"
              min={0.5}
              max={0.99}
              step={0.01}
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
              className="w-full accent-[var(--color-accent)] mt-2"
            />
          </Field>
        </div>

        <Field label="Tags">
          <div className="flex gap-2 flex-wrap mb-2">
            {tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[var(--color-surface-muted)] text-xs text-[var(--color-text-muted)]"
              >
                {t}
                <button type="button" onClick={() => setTags((prev) => prev.filter((x) => x !== t))}>
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
              placeholder="Nhập tag rồi Enter"
              className={`${inputCls} flex-1`}
            />
            <button type="button" onClick={addTag} className={secondaryBtnCls}>
              Thêm
            </button>
          </div>
        </Field>
      </section>

      {/* Question variants */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--color-text)] uppercase tracking-wide">
            Câu hỏi mẫu
          </h2>
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <HelpCircle className="w-3.5 h-3.5" />
            Dùng để tạo embedding RAG
          </span>
        </div>

        <div className="space-y-2">
          {questionVariants.map((v, idx) => (
            <div key={idx} className="flex gap-2">
              <input
                value={v}
                onChange={(e) => updateVariant(idx, e.target.value)}
                placeholder={`Câu hỏi mẫu ${idx + 1}`}
                className={`${inputCls} flex-1`}
              />
              {questionVariants.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeVariant(idx)}
                  className="p-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-red-500 hover:border-red-300 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
        </div>

        <button type="button" onClick={addVariant} className={`${secondaryBtnCls} gap-1.5`}>
          <Plus className="w-4 h-4" />
          Thêm câu hỏi mẫu
        </button>
      </section>

      {/* Answers */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-[var(--color-text)] uppercase tracking-wide">
          Câu trả lời TTS
        </h2>

        <Field label="Câu trả lời mặc định" required hint="Dùng khi không xác định được giới tính">
          <textarea
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            rows={3}
            placeholder="Phòng khám DoctorCheck mở cửa từ 7 giờ 30 sáng đến 11 giờ 30 trưa, anh/chị nhé."
            className={`${inputCls} resize-none`}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Câu trả lời — Nam" hint="Khi giọng có tần số thấp (<165Hz)">
            <textarea
              value={answerMale}
              onChange={(e) => setAnswerMale(e.target.value)}
              rows={3}
              placeholder="...anh nhé."
              className={`${inputCls} resize-none`}
            />
          </Field>
          <Field label="Câu trả lời — Nữ" hint="Khi giọng có tần số cao (≥165Hz)">
            <textarea
              value={answerFemale}
              onChange={(e) => setAnswerFemale(e.target.value)}
              rows={3}
              placeholder="...chị nhé."
              className={`${inputCls} resize-none`}
            />
          </Field>
        </div>
      </section>

      {initialData !== undefined && (
        <div className="flex items-center gap-3">
          <label className="text-sm text-[var(--color-text)] font-medium">Trạng thái</label>
          <button
            type="button"
            onClick={() => setIsActive((v) => !v)}
            className={[
              'relative inline-flex h-6 w-11 rounded-full transition-colors duration-200',
              isActive ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-border)]',
            ].join(' ')}
          >
            <span
              className={[
                'inline-block w-5 h-5 rounded-full bg-white shadow transform transition-transform duration-200 mt-0.5',
                isActive ? 'translate-x-5' : 'translate-x-0.5',
              ].join(' ')}
            />
          </button>
          <span className="text-sm text-[var(--color-text-muted)]">
            {isActive ? 'Active — dùng trong RAG' : 'Inactive — bị bỏ qua'}
          </span>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      <div className="flex items-center gap-3 pt-2 border-t border-[var(--color-border)]">
        <button type="submit" disabled={saving} className={primaryBtnCls}>
          {saving ? 'Đang lưu…' : submitLabel}
        </button>
        <button type="button" onClick={() => router.back()} className={secondaryBtnCls}>
          Huỷ
        </button>
      </div>
    </form>
  )
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string
  required?: boolean
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-[var(--color-text)]">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {hint && <p className="text-xs text-[var(--color-text-muted)]">{hint}</p>}
      {children}
    </div>
  )
}

const inputCls =
  'w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:border-transparent transition-shadow'

const primaryBtnCls =
  'inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors duration-[var(--duration-fast)]'

const secondaryBtnCls =
  'inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-border)] text-sm font-medium text-[var(--color-text)] hover:border-[var(--color-accent)] transition-colors duration-[var(--duration-fast)]'
