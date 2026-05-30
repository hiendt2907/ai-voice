'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import {
  BookOpen,
  Zap,
  Plus,
  ExternalLink,
  CheckCircle2,
  Clock,
  ChevronRight,
  X,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import type { KnowledgeArticle } from '@/lib/api/knowledge'
import type { NluDocument, NluDocType } from '@/lib/api/nlu'
import { TYPE_LABELS } from '@/lib/api/nlu'

interface RelatedData {
  kbArticles: KnowledgeArticle[]
  nluDocs: NluDocument[]
}

interface Props {
  scriptId: string
  initialData: RelatedData
  isNew?: boolean
}

/** Checklist item kinds the modal can operate on. */
type ChecklistItemKind = 'kb' | 'intent' | 'filler' | 'reprompt'

const NLU_TYPE_ORDER: NluDocType[] = ['intent', 'filler', 'reprompt', 'dialog_node']

const TOAST_DURATION_MS = 4000

/** GET endpoints may return a bare array or an envelope — normalize defensively. */
function unwrapArray<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object' && Array.isArray((payload as { data?: unknown }).data)) {
    return (payload as { data: T[] }).data
  }
  return []
}

export default function ScriptResourcePanel({ scriptId, initialData, isNew }: Props) {
  const [tab, setTab] = useState<'kb' | 'nlu'>('kb')
  const [related, setRelated] = useState<RelatedData>(initialData)
  const [modalItem, setModalItem] = useState<ChecklistItemKind | null>(null)

  const { kbArticles, nluDocs } = related

  const [toast, setToast] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  // Auto-dismiss toast after a short delay.
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), TOAST_DURATION_MS)
    return () => clearTimeout(timer)
  }, [toast])

  // Refetch via the portal proxy route (cookie-authenticated). Returns true on
  // success so callers can surface a clear error instead of swallowing failures.
  const refetchRelated = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch(`/api/scripts/${scriptId}/related`, { cache: 'no-store' })
      if (!res.ok) return false
      const data = (await res.json()) as Partial<RelatedData>
      setRelated({
        kbArticles: unwrapArray<KnowledgeArticle>(data.kbArticles),
        nluDocs: unwrapArray<NluDocument>(data.nluDocs),
      })
      return true
    } catch {
      return false
    }
  }, [scriptId])

  const handleModalClose = useCallback(
    async (changedCount: number) => {
      setModalItem(null)
      if (changedCount <= 0) return
      const ok = await refetchRelated()
      setToast(
        ok
          ? { kind: 'success', message: `Đã gắn ${changedCount} mục.` }
          : {
              kind: 'error',
              message: 'Đã gắn nhưng không tải lại được danh sách. Hãy tải lại trang.',
            },
      )
    },
    [refetchRelated],
  )

  const hasIntent = nluDocs.some((d) => d.type === 'intent')
  const hasFiller = nluDocs.some((d) => d.type === 'filler')
  const hasReprompt = nluDocs.some((d) => d.type === 'reprompt')

  const checklist: {
    key: ChecklistItemKind
    done: boolean
    label: string
    desc: string
  }[] = [
    {
      key: 'kb',
      done: kbArticles.length > 0,
      label: 'Thêm ít nhất 1 KB article',
      desc: 'Để bot tra cứu thông tin khi gọi',
    },
    {
      key: 'intent',
      done: hasIntent,
      label: 'Thêm NLU intent examples',
      desc: 'Để bot hiểu ý định người gọi',
    },
    {
      key: 'filler',
      done: hasFiller,
      label: 'Thêm NLU fillers',
      desc: 'Câu chờ và câu xác nhận',
    },
    {
      key: 'reprompt',
      done: hasReprompt,
      label: 'Thêm NLU reprompts',
      desc: 'Câu hỏi lại khi user không trả lời',
    },
  ]

  const allDone = checklist.every((c) => c.done)

  return (
    <div className="mt-8">
      {/* Checklist — hiện khi script mới hoặc còn item chưa hoàn thành */}
      {(isNew || !allDone) && (
        <div className="mb-6 rounded-xl border border-[oklch(88%_0.12_85)] bg-[oklch(98%_0.04_85)] p-5">
          <h3 className="text-sm font-semibold text-[oklch(42%_0.18_85)] mb-3">
            Checklist khởi động script
          </h3>
          <div className="space-y-2.5">
            {checklist.map((item) => (
              <div key={item.key} className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  {item.done ? (
                    <CheckCircle2 className="w-4 h-4 text-[var(--color-success)] shrink-0" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-[oklch(72%_0.12_85)] shrink-0" />
                  )}
                  <div>
                    <p className={`text-sm font-medium ${item.done ? 'text-[var(--color-text-muted)] line-through' : 'text-[var(--color-text)]'}`}>
                      {item.label}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)]">{item.desc}</p>
                  </div>
                </div>
                {!item.done && (
                  <button
                    type="button"
                    onClick={() => setModalItem(item.key)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-white border border-[oklch(82%_0.08_85)] text-[oklch(42%_0.18_85)] hover:bg-[oklch(96%_0.04_85)] transition-colors shrink-0"
                  >
                    Thêm ngay
                    <ChevronRight className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Panel header + tabs */}
      <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)] bg-[oklch(98.5%_0.003_250)]">
          <h2 className="text-sm font-semibold text-[var(--color-text)]">Tài nguyên Script</h2>
          <div className="flex">
            <TabBtn active={tab === 'kb'} onClick={() => setTab('kb')}>
              <BookOpen className="w-3.5 h-3.5" />
              Knowledge Base
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)]">
                {kbArticles.length}
              </span>
            </TabBtn>
            <TabBtn active={tab === 'nlu'} onClick={() => setTab('nlu')}>
              <Zap className="w-3.5 h-3.5" />
              NLU Content
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)]">
                {nluDocs.length}
              </span>
            </TabBtn>
          </div>
        </div>

        {/* KB Tab */}
        {tab === 'kb' && (
          <div>
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
              <p className="text-xs text-[var(--color-text-muted)]">
                Tài liệu KB để bot tra cứu trong cuộc gọi
              </p>
              <button
                type="button"
                onClick={() => setModalItem('kb')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors"
              >
                <Plus className="w-3 h-3" />
                Thêm KB article
              </button>
            </div>
            {kbArticles.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <BookOpen className="w-7 h-7 text-[var(--color-border)] mb-2.5" />
                <p className="text-sm text-[var(--color-text-muted)]">
                  Chưa có KB article nào cho script này.
                </p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  Thêm tài liệu để bot tra cứu khi gọi.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-[var(--color-border)]">
                {kbArticles.map((a) => (
                  <KbRow key={a.id} article={a} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* NLU Tab */}
        {tab === 'nlu' && (
          <div>
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
              <p className="text-xs text-[var(--color-text-muted)]">
                NLU docs giúp bot nhận diện ý định và phản hồi đúng
              </p>
              <Link
                href={`/nlu?scriptId=${scriptId}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors"
              >
                <Plus className="w-3 h-3" />
                Thêm NLU doc
              </Link>
            </div>
            {nluDocs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <Zap className="w-7 h-7 text-[var(--color-border)] mb-2.5" />
                <p className="text-sm text-[var(--color-text-muted)]">
                  Chưa có NLU document nào cho script này.
                </p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  Cần tối thiểu: intent examples, fillers, reprompts cho mỗi collect step.
                </p>
              </div>
            ) : (
              <div>
                {NLU_TYPE_ORDER.filter((t) => nluDocs.some((d) => d.type === t)).map((type) => (
                  <NluGroup
                    key={type}
                    type={type}
                    docs={nluDocs.filter((d) => d.type === type)}
                    scriptId={scriptId}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {modalItem && (
        <ChecklistModal scriptId={scriptId} item={modalItem} onClose={handleModalClose} />
      )}

      {toast && (
        <div
          role="status"
          aria-live="polite"
          className={[
            'fixed bottom-6 right-6 z-[60] flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium',
            toast.kind === 'success'
              ? 'bg-white border-[oklch(85%_0.12_150)] text-[var(--color-success)]'
              : 'bg-white border-[oklch(85%_0.1_25)] text-[oklch(50%_0.2_25)]',
          ].join(' ')}
        >
          {toast.kind === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          {toast.message}
        </div>
      )}
    </div>
  )
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
        active
          ? 'bg-white border border-[var(--color-border)] text-[var(--color-text)] shadow-sm'
          : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

function KbRow({ article }: { article: KnowledgeArticle }) {
  return (
    <div className="flex items-center justify-between px-5 py-3 hover:bg-[oklch(98.5%_0.003_250)] transition-colors">
      <div className="min-w-0">
        <p className="text-sm font-medium text-[var(--color-text)] truncate">{article.title}</p>
        <div className="flex items-center gap-2 mt-0.5">
          {article.category && (
            <span className="text-xs text-[var(--color-text-muted)]">{article.category}</span>
          )}
          {article.embeddingJson ? (
            <span className="inline-flex items-center gap-1 text-[10px] text-[var(--color-success)]">
              <CheckCircle2 className="w-3 h-3" />
              Embedded
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
              <Clock className="w-3 h-3" />
              Pending embed
            </span>
          )}
        </div>
      </div>
      <Link
        href={`/knowledge/${article.id}`}
        className="ml-3 p-1.5 rounded hover:bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors shrink-0"
        title="Xem KB article"
      >
        <ExternalLink className="w-3.5 h-3.5" />
      </Link>
    </div>
  )
}

function NluGroup({
  type,
  docs,
  scriptId,
}: {
  type: NluDocType
  docs: NluDocument[]
  scriptId: string
}) {
  return (
    <div>
      <div className="flex items-center justify-between px-5 py-2 bg-[oklch(98%_0.003_250)] border-b border-[var(--color-border)]">
        <span className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
          {TYPE_LABELS[type]}
        </span>
        <span className="text-xs text-[var(--color-text-muted)]">{docs.length} doc</span>
      </div>
      <div className="divide-y divide-[var(--color-border)]">
        {docs.map((doc) => (
          <NluRow key={doc.id} doc={doc} scriptId={scriptId} />
        ))}
      </div>
    </div>
  )
}

function NluRow({ doc, scriptId }: { doc: NluDocument; scriptId: string }) {
  return (
    <div className="flex items-center justify-between px-5 py-2.5 hover:bg-[oklch(98.5%_0.003_250)] transition-colors">
      <div className="min-w-0">
        <p className="text-xs font-mono text-[var(--color-text-muted)]">{doc.label}</p>
        <p className="text-sm text-[var(--color-text)] truncate mt-0.5">{doc.content}</p>
      </div>
      <div className="ml-3 shrink-0">
        {doc.embeddingJson ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-[var(--color-success)]" />
        ) : (
          <Clock className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
        )}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Checklist modal — attach existing resources or create new ones
 * ------------------------------------------------------------------------- */

const ITEM_IS_KB = (item: ChecklistItemKind): item is 'kb' => item === 'kb'

const MODAL_TITLES: Record<ChecklistItemKind, string> = {
  kb: 'Thêm KB article',
  intent: 'Thêm NLU intent examples',
  filler: 'Thêm NLU fillers',
  reprompt: 'Thêm NLU reprompts',
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Đã có lỗi xảy ra. Vui lòng thử lại.'
}

interface ChecklistModalProps {
  scriptId: string
  item: ChecklistItemKind
  // changedCount is the number of resources attached/created (0 = no change).
  onClose: (changedCount: number) => void
}

function ChecklistModal({ scriptId, item, onClose }: ChecklistModalProps) {
  const [modalTab, setModalTab] = useState<'pick' | 'create'>('pick')
  // Track how many resources were persisted so the parent can refetch + report.
  const [changedCount, setChangedCount] = useState(0)
  const isKb = ITEM_IS_KB(item)
  const nluType = isKb ? null : (item as NluDocType)

  // Close on Escape key.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose(changedCount)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, changedCount])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={MODAL_TITLES[item]}
    >
      <div
        className="absolute inset-0 bg-[rgba(0,0,0,0.4)]"
        onClick={() => onClose(changedCount)}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-lg max-h-[85vh] flex flex-col rounded-xl bg-white shadow-2xl border border-[var(--color-border)]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          <h3 className="text-sm font-semibold text-[var(--color-text)]">{MODAL_TITLES[item]}</h3>
          <button
            type="button"
            onClick={() => onClose(changedCount)}
            className="p-1 rounded hover:bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
            aria-label="Đóng"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 pt-3">
          <ModalTabBtn active={modalTab === 'pick'} onClick={() => setModalTab('pick')}>
            Chọn có sẵn
          </ModalTabBtn>
          <ModalTabBtn active={modalTab === 'create'} onClick={() => setModalTab('create')}>
            Tạo mới
          </ModalTabBtn>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {modalTab === 'pick' ? (
            <PickTab
              scriptId={scriptId}
              isKb={isKb}
              nluType={nluType}
              onAttached={(count) => {
                setChangedCount(count)
                onClose(count)
              }}
            />
          ) : (
            <CreateTab
              scriptId={scriptId}
              isKb={isKb}
              nluType={nluType}
              onCreated={() => {
                setChangedCount(1)
                onClose(1)
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function ModalTabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
        active
          ? 'bg-[var(--color-accent)] text-white'
          : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)]',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

/* ----- Tab 1: pick existing --------------------------------------------- */

function PickTab({
  scriptId,
  isKb,
  nluType,
  onAttached,
}: {
  scriptId: string
  isKb: boolean
  nluType: NluDocType | null
  onAttached: (count: number) => void
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [kbItems, setKbItems] = useState<KnowledgeArticle[]>([])
  const [nluItems, setNluItems] = useState<NluDocument[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (isKb) {
        const res = await fetch('/api/knowledge', { cache: 'no-store' })
        if (!res.ok) throw new Error('Không tải được danh sách KB.')
        const all = unwrapArray<KnowledgeArticle>(await res.json())
        setKbItems(all.filter((a) => !a.scriptId))
      } else if (nluType) {
        const res = await fetch(`/api/nlu?type=${nluType}`, { cache: 'no-store' })
        if (!res.ok) throw new Error('Không tải được danh sách NLU.')
        const all = unwrapArray<NluDocument>(await res.json())
        setNluItems(all.filter((d) => !d.scriptId && d.type === nluType))
      }
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [isKb, nluType])

  useEffect(() => {
    load()
  }, [load])

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleAttach = async () => {
    if (selected.size === 0) return
    setSaving(true)
    setError(null)
    try {
      const ids = Array.from(selected)
      await Promise.all(
        ids.map(async (id) => {
          const url = isKb ? `/api/knowledge/${id}` : `/api/nlu?id=${id}`
          const res = await fetch(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scriptId }),
          })
          if (!res.ok) throw new Error('Gắn tài nguyên thất bại.')
        }),
      )
      const attachedCount = ids.length
      setSelected(new Set())
      // Closes the modal and triggers the parent panel to refetch, so the
      // attached resources show up immediately.
      onAttached(attachedCount)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10 text-[var(--color-text-muted)]">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    )
  }

  const rows: { id: string; primary: string; secondary: string }[] = isKb
    ? kbItems.map((a) => ({ id: a.id, primary: a.title, secondary: a.answerText }))
    : nluItems.map((d) => ({ id: d.id, primary: d.label, secondary: d.content }))

  return (
    <div>
      {error && <ModalError message={error} />}

      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            Không có tài nguyên rảnh nào để gắn.
          </p>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">
            Tất cả đã được gắn với script khác — hãy chuyển sang tab Tạo mới.
          </p>
        </div>
      ) : (
        <>
          <ul className="space-y-1.5 mb-4">
            {rows.map((row) => {
              const checked = selected.has(row.id)
              return (
                <li key={row.id}>
                  <label
                    className={[
                      'flex items-start gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors',
                      checked
                        ? 'border-[var(--color-accent)] bg-[var(--color-surface-overlay)]'
                        : 'border-[var(--color-border)] hover:bg-[oklch(98.5%_0.003_250)]',
                    ].join(' ')}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(row.id)}
                      className="mt-0.5 accent-[var(--color-accent)]"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[var(--color-text)] truncate">
                        {row.primary}
                      </p>
                      <p className="text-xs text-[var(--color-text-muted)] line-clamp-2">
                        {row.secondary}
                      </p>
                    </div>
                  </label>
                </li>
              )
            })}
          </ul>

          <button
            type="button"
            onClick={handleAttach}
            disabled={selected.size === 0 || saving}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Gắn đã chọn{selected.size > 0 ? ` (${selected.size})` : ''}
          </button>
        </>
      )}
    </div>
  )
}

/* ----- Tab 2: create new ------------------------------------------------- */

function CreateTab({
  scriptId,
  isKb,
  nluType,
  onCreated,
}: {
  scriptId: string
  isKb: boolean
  nluType: NluDocType | null
  onCreated: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // KB fields
  const [title, setTitle] = useState('')
  const [answerText, setAnswerText] = useState('')
  const [questionVariant, setQuestionVariant] = useState('')

  // NLU fields
  const [label, setLabel] = useState('')
  const [content, setContent] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (isKb) {
        const res = await fetch('/api/knowledge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title.trim(),
            answerText: answerText.trim(),
            questionVariants: [questionVariant.trim()],
            scriptId,
          }),
        })
        if (!res.ok) throw new Error('Tạo KB article thất bại.')
      } else if (nluType) {
        const res = await fetch('/api/nlu', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: nluType,
            label: label.trim(),
            content: content.trim(),
            scriptId,
          }),
        })
        if (!res.ok) throw new Error('Tạo NLU doc thất bại.')
      }
      onCreated()
    } catch (e) {
      setError(getErrorMessage(e))
      setSaving(false)
    }
  }

  const kbValid = title.trim() && answerText.trim() && questionVariant.trim()
  const nluValid = label.trim() && content.trim()
  const canSubmit = isKb ? Boolean(kbValid) : Boolean(nluValid)

  return (
    <form onSubmit={handleSubmit} className="space-y-3.5">
      {error && <ModalError message={error} />}

      {isKb ? (
        <>
          <Field label="Tiêu đề" required>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className={inputCls}
              placeholder="VD: Giờ làm việc phòng khám"
            />
          </Field>
          <Field label="Câu hỏi ví dụ" required>
            <input
              type="text"
              value={questionVariant}
              onChange={(e) => setQuestionVariant(e.target.value)}
              required
              className={inputCls}
              placeholder="VD: Phòng khám mở cửa lúc mấy giờ?"
            />
          </Field>
          <Field label="Nội dung trả lời" required>
            <textarea
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              required
              rows={4}
              className={inputCls}
              placeholder="VD: Phòng khám mở cửa từ 7h đến 20h mỗi ngày."
            />
          </Field>
        </>
      ) : (
        <>
          <Field label="Loại">
            <input
              type="text"
              value={nluType ? TYPE_LABELS[nluType] : ''}
              readOnly
              className={`${inputCls} bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] cursor-not-allowed`}
            />
          </Field>
          <Field label="Label" required>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              required
              className={inputCls}
              placeholder="VD: book_appointment"
            />
          </Field>
          <Field label="Nội dung" required>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required
              rows={3}
              className={inputCls}
              placeholder="VD: Tôi muốn đặt lịch khám"
            />
          </Field>
        </>
      )}

      <div className="pt-1">
        <button
          type="submit"
          disabled={!canSubmit || saving}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
          Tạo và gắn
        </button>
      </div>
    </form>
  )
}

const inputCls =
  'w-full px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm text-[var(--color-text)] bg-white focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:border-transparent transition-shadow'

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
        {label}
        {required && <span className="text-[var(--color-danger,oklch(58%_0.2_25))] ml-0.5">*</span>}
      </span>
      {children}
    </label>
  )
}

function ModalError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 mb-3 px-3 py-2 rounded-lg bg-[oklch(96%_0.05_25)] border border-[oklch(85%_0.1_25)]">
      <AlertCircle className="w-4 h-4 text-[oklch(55%_0.2_25)] shrink-0 mt-0.5" />
      <p className="text-xs text-[oklch(45%_0.18_25)]">{message}</p>
    </div>
  )
}
