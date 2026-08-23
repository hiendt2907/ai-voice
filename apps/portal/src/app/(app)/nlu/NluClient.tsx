'use client'

import { useState, useTransition } from 'react'
import { Plus, Trash2, Zap, CheckCircle2, Clock, AlertCircle, ChevronDown } from 'lucide-react'
import type { NluDocument, NluDocType } from '@/lib/api/nlu'
import { TYPE_LABELS, TYPE_DESCRIPTIONS, FILLER_CONTEXTS } from '@/lib/api/nlu'

const TABS: { key: NluDocType | 'all'; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'intent', label: 'Intent Examples' },
  { key: 'filler', label: 'Fillers' },
  { key: 'reprompt', label: 'Reprompts' },
  { key: 'dialog_node', label: 'Dialog Nodes' },
]

interface Props {
  initialDocs: NluDocument[]
  scriptId?: string
  defaultType?: NluDocType
}

export default function NluClient({ initialDocs, scriptId, defaultType }: Props) {
  const [docs, setDocs] = useState(initialDocs)
  const [activeTab, setActiveTab] = useState<NluDocType | 'all'>(defaultType ?? 'all')
  const [showForm, setShowForm] = useState(!!defaultType)
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  const visible = activeTab === 'all' ? docs : docs.filter((d) => d.type === activeTab)

  async function handleCreate(data: Partial<NluDocument>) {
    setError(null)
    try {
      const payload = scriptId ? { ...data, scriptId } : data
      const res = await fetch('/api/nlu', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const created = await res.json() as NluDocument
      setDocs((prev) => [created, ...prev])
      setShowForm(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi tạo document')
    }
  }

  async function handleToggle(doc: NluDocument) {
    startTransition(async () => {
      try {
        const res = await fetch(`/api/nlu?id=${doc.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ isActive: !doc.isActive }),
        })
        if (!res.ok) throw new Error(await res.text())
        const updated = await res.json() as NluDocument
        setDocs((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
      } catch {
        setError('Lỗi cập nhật trạng thái')
      }
    })
  }

  async function handleDelete(id: string) {
    if (!confirm('Xóa document này?')) return
    try {
      const res = await fetch(`/api/nlu?id=${id}`, { method: 'DELETE' })
      if (!res.ok && res.status !== 204) throw new Error(await res.text())
      setDocs((prev) => prev.filter((d) => d.id !== id))
    } catch {
      setError('Lỗi xóa document')
    }
  }

  const embedded = docs.filter((d) => d.embeddingJson).length
  const active = docs.filter((d) => d.isActive).length

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Script context banner */}
      {scriptId && (
        <div className="mb-4 flex items-center justify-between px-4 py-2.5 rounded-lg bg-[oklch(97%_0.03_250)] border border-[oklch(88%_0.06_250)] text-sm">
          <span className="text-[var(--color-text-muted)]">
            Đang xem NLU docs của script · Documents mới sẽ được liên kết tự động
          </span>
          <a
            href={`/scripts/${scriptId}`}
            className="text-[var(--color-accent)] font-medium hover:underline ml-4 shrink-0"
          >
            ← Quay lại Script
          </a>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">
            NLU Content
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            {docs.length} documents · {active} active · {embedded} đã embed
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] transition-colors"
        >
          <Plus className="w-4 h-4" />
          Thêm document
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 mb-6 rounded-lg bg-[var(--color-surface-muted)] w-fit">
        {TABS.map((tab) => {
          const count = tab.key === 'all' ? docs.length : docs.filter((d) => d.type === tab.key).length
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={[
                'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                activeTab === tab.key
                  ? 'bg-white text-[var(--color-text)] shadow-sm'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]',
              ].join(' ')}
            >
              {tab.label}
              <span className="ml-1.5 text-xs text-[var(--color-text-muted)]">({count})</span>
            </button>
          )
        })}
      </div>

      {/* Create form */}
      {showForm && (
        <CreateForm
          defaultType={activeTab === 'all' ? 'intent' : activeTab}
          onSubmit={handleCreate}
          onCancel={() => setShowForm(false)}
        />
      )}

      {/* Doc list */}
      {visible.length === 0 ? (
        <EmptyState type={activeTab} />
      ) : (
        <div className="space-y-2">
          {visible.map((doc) => (
            <DocRow
              key={doc.id}
              doc={doc}
              onToggle={handleToggle}
              onDelete={handleDelete}
              disabled={isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function DocRow({
  doc,
  onToggle,
  onDelete,
  disabled,
}: {
  doc: NluDocument
  onToggle: (d: NluDocument) => void
  onDelete: (id: string) => void
  disabled: boolean
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={[
      'rounded-lg border bg-white transition-colors',
      doc.isActive ? 'border-[var(--color-border)]' : 'border-[var(--color-border)] opacity-60',
    ].join(' ')}>
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Type badge */}
        <span className={[
          'shrink-0 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide',
          doc.type === 'intent' ? 'bg-blue-50 text-blue-600' :
          doc.type === 'filler' ? 'bg-green-50 text-green-600' :
          doc.type === 'reprompt' ? 'bg-amber-50 text-amber-600' :
          'bg-purple-50 text-purple-600',
        ].join(' ')}>
          {TYPE_LABELS[doc.type]}
        </span>

        {/* Label */}
        <span className="text-xs font-mono text-[var(--color-text-muted)] shrink-0 min-w-[120px]">
          {doc.label}
        </span>

        {/* Content preview */}
        <span className="flex-1 text-sm text-[var(--color-text)] truncate min-w-0">
          {doc.content}
        </span>

        {/* Embed status */}
        <span title={doc.embeddingJson ? 'Đã embed' : 'Chưa embed'}>
          {doc.embeddingJson ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
          ) : (
            <Clock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          )}
        </span>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-muted)] transition-colors"
            title="Chi tiết"
          >
            <ChevronDown className={['w-3.5 h-3.5 transition-transform', expanded ? 'rotate-180' : ''].join(' ')} />
          </button>
          <button
            onClick={() => onToggle(doc)}
            disabled={disabled}
            className={[
              'p-1 rounded text-xs font-medium transition-colors',
              doc.isActive
                ? 'text-emerald-600 hover:bg-emerald-50'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]',
            ].join(' ')}
            title={doc.isActive ? 'Deactivate' : 'Activate'}
          >
            <Zap className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onDelete(doc.id)}
            className="p-1 rounded text-[var(--color-text-muted)] hover:text-red-500 hover:bg-red-50 transition-colors"
            title="Xóa"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-[var(--color-border)] px-4 py-3 text-xs text-[var(--color-text-muted)] space-y-1 bg-[var(--color-surface-muted)]">
          <p><span className="font-medium">Content:</span> {doc.content}</p>
          {doc.campaignId && <p><span className="font-medium">Campaign:</span> {doc.campaignId}</p>}
          {doc.scriptId && <p><span className="font-medium">Script:</span> {doc.scriptId}</p>}
          {Object.keys(doc.meta ?? {}).length > 0 && (
            <p><span className="font-medium">Meta:</span> {JSON.stringify(doc.meta)}</p>
          )}
          <p><span className="font-medium">Embed:</span> {doc.embeddingJson ? '✓ dim=' + (JSON.parse(doc.embeddingJson) as number[]).length : '— chưa embed'}</p>
          <p><span className="font-medium">Created:</span> {new Date(doc.createdAt).toLocaleString('vi-VN')}</p>
        </div>
      )}
    </div>
  )
}

function CreateForm({
  defaultType,
  onSubmit,
  onCancel,
}: {
  defaultType: NluDocType
  onSubmit: (data: Partial<NluDocument>) => void | Promise<void>
  onCancel: () => void
}) {
  const [type, setType] = useState<NluDocType>(defaultType)
  const [label, setLabel] = useState('')
  const [content, setContent] = useState('')
  const [metaRaw, setMetaRaw] = useState('{}')
  const [metaError, setMetaError] = useState(false)
  // Chống double-submit: bấm nhanh 2 lần trước khi request đầu hoàn tất sẽ tạo trùng document.
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting) return
    let meta: Record<string, unknown> = {}
    try {
      meta = JSON.parse(metaRaw) as Record<string, unknown>
      setMetaError(false)
    } catch {
      setMetaError(true)
      return
    }
    setSubmitting(true)
    try {
      await onSubmit({ type, label: label.trim(), content: content.trim(), meta })
    } finally {
      setSubmitting(false)
    }
  }

  const typeDescription = TYPE_DESCRIPTIONS[type]

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="mb-6 p-5 rounded-xl border border-[var(--color-accent)] bg-blue-50/30 space-y-4">
      <h3 className="text-sm font-semibold text-[var(--color-text)]">Tạo NLU document mới</h3>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Loại</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as NluDocType)}
            className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          >
            {(['intent', 'filler', 'reprompt', 'dialog_node'] as NluDocType[]).map((t) => (
              <option key={t} value={t}>{TYPE_LABELS[t]}</option>
            ))}
          </select>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-1">{typeDescription}</p>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
            Label {type === 'filler' ? '(context)' : type === 'intent' ? '(intent name)' : '(step_id)'}
          </label>
          {type === 'filler' ? (
            <select
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            >
              <option value="">-- chọn context --</option>
              {FILLER_CONTEXTS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              required
              placeholder={type === 'intent' ? 'book_appointment' : 'collect_specialty'}
              className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            />
          )}
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Content (text sẽ được embed)</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          required
          rows={3}
          placeholder={
            type === 'intent' ? 'muốn đặt lịch khám tim mạch ngày mai' :
            type === 'filler' ? 'Dạ,' :
            'Anh/chị muốn khám chuyên khoa gì ạ?'
          }
          className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] resize-none"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
          Meta (JSON) {type === 'intent' && '— {"slots": {"specialty": "Tim mạch"}}'}
          {type === 'reprompt' && '— {"order": 0}'}
        </label>
        <input
          value={metaRaw}
          onChange={(e) => { setMetaRaw(e.target.value); setMetaError(false) }}
          className={[
            'w-full px-3 py-2 rounded-lg border text-sm font-mono text-[var(--color-text)] focus:outline-none focus:ring-2',
            metaError ? 'border-red-400 focus:ring-red-400 bg-red-50' : 'border-[var(--color-border)] bg-white focus:ring-[var(--color-accent)]',
          ].join(' ')}
        />
        {metaError && <p className="text-[10px] text-red-500 mt-1">JSON không hợp lệ</p>}
      </div>

      <div className="flex gap-3 justify-end">
        <button type="button" onClick={onCancel} disabled={submitting} className="px-4 py-2 rounded-lg border border-[var(--color-border)] text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] disabled:opacity-50 transition-colors">
          Hủy
        </button>
        <button type="submit" disabled={submitting} className="px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors">
          {submitting ? 'Đang tạo…' : 'Tạo & Embed'}
        </button>
      </div>
    </form>
  )
}

function EmptyState({ type }: { type: NluDocType | 'all' }) {
  return (
    <div className="py-16 flex flex-col items-center gap-3 text-[var(--color-text-muted)]">
      <Zap className="w-8 h-8 opacity-30" />
      <p className="text-sm">
        {type === 'all' ? 'Chưa có NLU document nào' : `Chưa có ${TYPE_LABELS[type as NluDocType] ?? type} nào`}
      </p>
      <p className="text-xs opacity-60">Nhấn "Thêm document" để bắt đầu</p>
    </div>
  )
}
