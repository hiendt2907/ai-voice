'use client'

import { useState, use, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft, Loader2, CheckCircle2, XCircle, AlertTriangle,
  ChevronRight, ChevronDown, Send, Globe, BookOpen, Mic,
} from 'lucide-react'
import type { LintResult } from '@/lib/api/scripts'
import { KbCategoryTree } from './KbCategoryTree'

type Template = 'basic' | 'advanced' | 'custom'

interface AiDrivenBody {
  type: 'ai_driven'
  execution_mode: 'rag_assisted' | 'fsm'
  version: string
  greeting: string
  persona: {
    fillers: string[]
    barge_in: boolean
    gender_detect: boolean
  }
  rag: { enabled: boolean; collection: string; linkedKbTags: string[] }
  ragFallbackMessage: string
  escalation: {
    telegram: boolean
    bot_token: string
    chat_id: string
    template: string
    waiting_message: string
  }
  fallback_message: string
}

const FILLERS_ALL = ['Dạ', 'À', 'Vâng ạ', 'Dạ vâng', 'Ừm']

function buildBody(
  version: string,
  greeting: string,
  fillers: string[],
  bargeIn: boolean,
  genderDetect: boolean,
  ragEnabled: boolean,
  ragCollection: string,
  linkedKbTags: string[],
  ragFallbackMessage: string,
  telegramEnabled: boolean,
  telegramToken: string,
  telegramChatId: string,
  telegramTemplate: string,
  waitingMsg: string,
  fallbackMsg: string,
): AiDrivenBody {
  return {
    type: 'ai_driven',
    execution_mode: ragEnabled ? 'rag_assisted' : 'fsm',
    version,
    greeting,
    persona: { fillers, barge_in: bargeIn, gender_detect: genderDetect },
    rag: { enabled: ragEnabled, collection: ragCollection, linkedKbTags },
    ragFallbackMessage: ragFallbackMessage || 'Dạ em sẽ kiểm tra và phản hồi lại anh/chị sớm ạ',
    escalation: {
      telegram: telegramEnabled,
      bot_token: telegramToken,
      chat_id: telegramChatId,
      template: telegramTemplate,
      waiting_message: waitingMsg,
    },
    fallback_message: fallbackMsg,
  }
}

function Section({ title, icon, children, open, onToggle }: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  open: boolean
  onToggle: () => void
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-[var(--color-surface-overlay)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="w-7 h-7 rounded-lg bg-[oklch(96%_0.03_250)] flex items-center justify-center text-[var(--color-accent)]">
            {icon}
          </span>
          <span className="text-sm font-semibold text-[var(--color-text)]">{title}</span>
        </div>
        {open ? <ChevronDown className="w-4 h-4 text-[var(--color-text-muted)]" /> : <ChevronRight className="w-4 h-4 text-[var(--color-text-muted)]" />}
      </button>
      {open && <div className="px-5 pb-5 space-y-4 border-t border-[var(--color-border)]">{children}</div>}
    </div>
  )
}

function Toggle({ label, description, checked, onChange }: { label: string; description?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <div className="relative mt-0.5">
        <input type="checkbox" className="sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <div className={['w-10 h-6 rounded-full transition-colors', checked ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-border)]'].join(' ')} />
        <div className={['absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform', checked ? 'translate-x-5' : 'translate-x-1'].join(' ')} />
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--color-text)]">{label}</p>
        {description && <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{description}</p>}
      </div>
    </label>
  )
}

export default function NewVersionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()

  // Meta
  const [version, setVersion] = useState('1.0.0')
  const [template, setTemplate] = useState<Template>('advanced')

  // Section 2: Greeting
  const [greeting, setGreeting] = useState('Dạ, Doctor Check xin nghe ạ')

  // Section 3: Persona
  const [fillers, setFillers] = useState<string[]>(['Dạ', 'À', 'Vâng ạ', 'Dạ vâng'])
  const [bargeIn, setBargeIn] = useState(true)
  const [genderDetect, setGenderDetect] = useState(true)

  // Section 4: RAG
  const [ragEnabled, setRagEnabled] = useState(true)
  const [ragCollection, setRagCollection] = useState('doctorcheck_v1')
  const [linkedKbTags, setLinkedKbTags] = useState<string[]>([])
  const [ragFallbackMessage, setRagFallbackMessage] = useState('')
  const [kbArticles, setKbArticles] = useState<Array<{ id: string; title: string; category: string | null; tags: string[] }>>([])
  const [kbLoading, setKbLoading] = useState(false)

  // Section 5: Escalation
  const [telegramEnabled, setTelegramEnabled] = useState(true)
  const [telegramToken, setTelegramToken] = useState('')
  const [telegramChatId, setTelegramChatId] = useState('')
  const [telegramTemplate, setTelegramTemplate] = useState('❓ {question}\n📞 Cuộc gọi: {session_id}')
  const [waitingMsg, setWaitingMsg] = useState('Dạ em đã gửi câu hỏi lên đội bác sĩ, chút nữa em phản hồi anh/chị ngay ạ')
  const [fallbackMsg, setFallbackMsg] = useState('Dạ để em kiểm tra thêm thông tin ạ')

  // UI state
  const [openSections, setOpenSections] = useState({ greeting: true, persona: false, rag: false, escalation: false })

  // Fetch KB articles when RAG section opens
  useEffect(() => {
    if (!openSections.rag || kbArticles.length > 0 || kbLoading) return
    setKbLoading(true)
    fetch('/api/v1/knowledge', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Array<{ id: string; title: string; category: string | null; tags: string[] }>) => {
        setKbArticles(Array.isArray(data) ? data : [])
      })
      .catch(() => {})
      .finally(() => setKbLoading(false))
  }, [openSections.rag, kbArticles.length, kbLoading])
  const [saving, setSaving] = useState(false)
  const [lintResult, setLintResult] = useState<LintResult | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  function toggleSection(key: keyof typeof openSections) {
    setOpenSections((s) => ({ ...s, [key]: !s[key] }))
  }

  function toggleFiller(f: string) {
    setFillers((prev) => prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f])
  }

  function applyTemplate(t: Template) {
    setTemplate(t)
    if (t === 'basic') {
      setRagEnabled(false)
      setTelegramEnabled(false)
      setBargeIn(false)
      setGenderDetect(false)
      setFillers(['Dạ'])
    } else if (t === 'advanced') {
      setRagEnabled(true)
      setTelegramEnabled(true)
      setBargeIn(true)
      setGenderDetect(true)
      setFillers(['Dạ', 'À', 'Vâng ạ', 'Dạ vâng'])
    }
  }

  async function handleSave() {
    if (fillers.length === 0) { setErrorMsg('Chọn ít nhất một filler word'); return }
    setSaving(true)
    setErrorMsg(null)
    setLintResult(null)
    try {
      const body = buildBody(
        version, greeting, fillers, bargeIn, genderDetect,
        ragEnabled, ragCollection, linkedKbTags, ragFallbackMessage,
        telegramEnabled, telegramToken, telegramChatId, telegramTemplate, waitingMsg,
        fallbackMsg,
      )

      const validateRes = await fetch('/api/v1/scripts/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
      })
      const lint = (await validateRes.json()) as LintResult
      setLintResult(lint)
      if (!lint.valid) return

      const res = await fetch(`/api/v1/scripts/${id}/versions`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version, body }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        setErrorMsg(err.message ?? 'Lỗi lưu version')
        return
      }
      router.push(`/scripts/${id}`)
    } catch {
      setErrorMsg('Không thể kết nối tới server')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <Link
        href={`/scripts/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Campaign Detail
      </Link>

      <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight mb-1">
        Tạo Script Version
      </h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-8">
        AI-driven script — cấu hình luồng hội thoại thông qua các tham số
      </p>

      <div className="space-y-5">
        {/* Version */}
        <div className="rounded-xl border border-[var(--color-border)] bg-white p-5">
          <div className="flex items-center gap-4">
            <div>
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Version</label>
              <input
                type="text"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="1.0.0"
                className="input w-36"
              />
              <p className="text-xs text-[var(--color-text-muted)] mt-1">Semver: MAJOR.MINOR.PATCH</p>
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Template</label>
              <div className="flex gap-2">
                {(['basic', 'advanced', 'custom'] as Template[]).map((t) => {
                  const labels = { basic: 'Basic', advanced: 'Advanced', custom: 'Custom' }
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() => applyTemplate(t)}
                      className={[
                        'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                        template === t
                          ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                          : 'bg-white text-[var(--color-text)] border-[var(--color-border)] hover:bg-[var(--color-surface-overlay)]',
                      ].join(' ')}
                    >
                      {labels[t]}
                    </button>
                  )
                })}
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">Basic: greeting + fallback · Advanced: đầy đủ RAG + Telegram</p>
            </div>
          </div>
        </div>

        {/* Section 2: Greeting */}
        <Section title="Lời chào đầu tiên" icon={<Mic className="w-3.5 h-3.5" />} open={openSections.greeting} onToggle={() => toggleSection('greeting')}>
          <div className="pt-4">
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Câu chào</label>
            <textarea
              value={greeting}
              onChange={(e) => setGreeting(e.target.value)}
              rows={2}
              className="input resize-none"
              placeholder="Dạ, Doctor Check xin nghe ạ"
            />
            <p className="text-xs text-[var(--color-text-muted)] mt-1">Câu này sẽ được TTS đọc ngay khi kết nối cuộc gọi</p>
          </div>
        </Section>

        {/* Section 3: Persona */}
        <Section title="Cấu hình hội thoại" icon={<BookOpen className="w-3.5 h-3.5" />} open={openSections.persona} onToggle={() => toggleSection('persona')}>
          <div className="pt-4 space-y-4">
            <div>
              <p className="text-sm font-medium text-[var(--color-text)] mb-2">Filler words</p>
              <p className="text-xs text-[var(--color-text-muted)] mb-3">Từ đệm AI dùng để kéo dài thời gian xử lý, tạo cảm giác tự nhiên</p>
              <div className="flex flex-wrap gap-2">
                {FILLERS_ALL.map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => toggleFiller(f)}
                    className={[
                      'px-3 py-1 rounded-lg text-xs font-medium border transition-colors',
                      fillers.includes(f)
                        ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                        : 'bg-white text-[var(--color-text)] border-[var(--color-border)] hover:bg-[var(--color-surface-overlay)]',
                    ].join(' ')}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <Toggle
              label="Barge-in"
              description="Khi khách chen ngang → AI dừng phát lại ngay + chèn filler word"
              checked={bargeIn}
              onChange={setBargeIn}
            />
            <Toggle
              label="Nhận diện giới tính"
              description="Phân tích pitch giọng để xưng hô anh/chị phù hợp"
              checked={genderDetect}
              onChange={setGenderDetect}
            />
            <div>
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Câu fallback</label>
              <input
                type="text"
                value={fallbackMsg}
                onChange={(e) => setFallbackMsg(e.target.value)}
                className="input"
                placeholder="Dạ để em kiểm tra thêm thông tin ạ"
              />
              <p className="text-xs text-[var(--color-text-muted)] mt-1">Câu trả lời khi AI không có đủ thông tin</p>
            </div>
          </div>
        </Section>

        {/* Section 4: RAG */}
        <Section title="RAG Knowledge Base" icon={<BookOpen className="w-3.5 h-3.5" />} open={openSections.rag} onToggle={() => toggleSection('rag')}>
          <div className="pt-4 space-y-4">
            <Toggle
              label="Bật RAG (rag_assisted mode)"
              description="STT → embed → vector search KB → TTS template answer · Low confidence → Telegram handoff"
              checked={ragEnabled}
              onChange={setRagEnabled}
            />
            {ragEnabled && (
              <>
                {/* KB Category Tree */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium text-[var(--color-text)]">
                      Danh mục KB liên kết
                    </label>
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {linkedKbTags.length === 0
                        ? 'Tìm toàn bộ KB'
                        : `${linkedKbTags.length} danh mục đã chọn`}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)] mb-3">
                    Chọn danh mục để giới hạn RAG search — tránh câu trả lời lạc đề giữa các campaign.
                    Bỏ trống = tìm toàn bộ KB.
                  </p>
                  <KbCategoryTree
                    articles={kbArticles}
                    selected={linkedKbTags}
                    onChange={setLinkedKbTags}
                    loading={kbLoading}
                  />
                </div>

                {/* RAG Fallback message */}
                <div>
                  <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
                    Câu khi không tìm thấy trong KB
                  </label>
                  <input
                    type="text"
                    value={ragFallbackMessage}
                    onChange={(e) => setRagFallbackMessage(e.target.value)}
                    className="input"
                    placeholder="Dạ em sẽ kiểm tra và phản hồi lại anh/chị sớm ạ"
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">
                    TTS đọc trước khi escalate lên Telegram (nếu bật)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Collection name</label>
                  <input
                    type="text"
                    value={ragCollection}
                    onChange={(e) => setRagCollection(e.target.value)}
                    className="input"
                    placeholder="doctorcheck_v1"
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">
                    Flow: STT → embed → search(danh mục đã chọn) → score ≥ threshold → TTS · else → Telegram
                  </p>
                </div>
              </>
            )}
          </div>
        </Section>

        {/* Section 5: Escalation */}
        <Section title="Telegram Escalation" icon={<Send className="w-3.5 h-3.5" />} open={openSections.escalation} onToggle={() => toggleSection('escalation')}>
          <div className="pt-4 space-y-4">
            <Toggle
              label="Bật Telegram escalation"
              description="Khi RAG không có đáp án → gửi câu hỏi lên nhóm Telegram"
              checked={telegramEnabled}
              onChange={setTelegramEnabled}
            />
            {telegramEnabled && (
              <>
                <div>
                  <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Bot Token</label>
                  <input
                    type="password"
                    value={telegramToken}
                    onChange={(e) => setTelegramToken(e.target.value)}
                    className="input"
                    placeholder="1234567890:ABCdefGHI..."
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">Lấy từ @BotFather → /newbot → copy token</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Chat ID</label>
                  <input
                    type="text"
                    value={telegramChatId}
                    onChange={(e) => setTelegramChatId(e.target.value)}
                    className="input"
                    placeholder="-1001234567890"
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">ID nhóm nhận thông báo (số âm, bắt đầu -100)</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Template tin nhắn</label>
                  <textarea
                    value={telegramTemplate}
                    onChange={(e) => setTelegramTemplate(e.target.value)}
                    rows={3}
                    className="input font-mono text-xs resize-none"
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">Biến: {'{question}'}, {'{session_id}'}</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">Câu chờ escalation</label>
                  <input
                    type="text"
                    value={waitingMsg}
                    onChange={(e) => setWaitingMsg(e.target.value)}
                    className="input"
                    placeholder="Dạ em đã gửi câu hỏi lên đội bác sĩ..."
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">Câu TTS đọc trong khi chờ nhân viên phản hồi</p>
                </div>
              </>
            )}
          </div>
        </Section>

        {/* Lint result */}
        {lintResult && (
          <div className={['rounded-xl border p-4 space-y-2', lintResult.valid ? 'bg-[oklch(97%_0.04_145)] border-[oklch(85%_0.09_145)]' : 'bg-[oklch(97%_0.04_27)] border-[oklch(85%_0.08_27)]'].join(' ')}>
            <div className="flex items-center gap-2">
              {lintResult.valid
                ? <CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" />
                : <XCircle className="w-4 h-4 text-[var(--color-danger)]" />}
              <span className="text-sm font-semibold text-[var(--color-text)]">
                {lintResult.valid ? 'Script hợp lệ' : `${lintResult.errors.length} lỗi cần sửa`}
              </span>
            </div>
            {lintResult.errors.map((e) => (
              <div key={`${e.code}-${e.field}`} className="flex gap-2 text-sm">
                <span className="shrink-0 font-mono text-xs font-bold text-[var(--color-danger)] pt-0.5">{e.code}</span>
                <p className="text-[var(--color-text)]">{e.message}</p>
              </div>
            ))}
            {lintResult.warnings.map((w) => (
              <div key={`${w.code}-${w.field}`} className="flex gap-2 text-sm">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-[var(--color-warning)] mt-0.5" />
                <p className="text-[var(--color-text-muted)]">{w.message}</p>
              </div>
            ))}
          </div>
        )}

        {errorMsg && (
          <p className="text-sm text-[var(--color-danger)] flex items-center gap-1.5">
            <XCircle className="w-4 h-4 shrink-0" />
            {errorMsg}
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Lưu Draft
          </button>
          <Link
            href={`/scripts/${id}`}
            className="px-4 py-2.5 rounded-lg border border-[var(--color-border)] text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)] transition-colors"
          >
            Hủy
          </Link>
          <Link
            href="#"
            onClick={(e) => {
              e.preventDefault()
              const body = buildBody(version, greeting, fillers, bargeIn, genderDetect, ragEnabled, ragCollection, linkedKbTags, ragFallbackMessage, telegramEnabled, telegramToken, telegramChatId, telegramTemplate, waitingMsg, fallbackMsg)
              const blob = new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a'); a.href = url; a.download = `script_${version}.json`; a.click()
              URL.revokeObjectURL(url)
            }}
            className="ml-auto text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] flex items-center gap-1 transition-colors"
          >
            <Globe className="w-3.5 h-3.5" />
            Xem JSON
          </Link>
        </div>
      </div>
    </div>
  )
}
