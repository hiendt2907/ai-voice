'use client'

import { useState, use, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Loader2, CheckCircle2, XCircle, AlertTriangle, Volume2, VolumeX } from 'lucide-react'
import type { LintResult } from '@/lib/api/scripts'

type Beat = { text: string; pause_after?: string }
type Variant = { beats: Beat[] }
type Step = { id: string; type: string; variants?: Variant[] }
type ScriptBody = { entry_step?: string; steps?: Step[] }

function extractBeats(body: ScriptBody): Beat[] {
  const steps = body.steps ?? []
  const visited = new Set<string>()
  const beats: Beat[] = []
  let stepId: string | undefined = body.entry_step
  while (stepId && !visited.has(stepId)) {
    visited.add(stepId)
    const step = steps.find((s) => s.id === stepId)
    if (!step) break
    const variant = step.variants?.[0]
    if (variant?.beats) beats.push(...variant.beats)
    stepId = undefined
  }
  return beats
}

const PAUSE_MS: Record<string, number> = {
  none: 0, micro: 50, short: 150, breath: 300, medium: 500, long: 800, turn: 1200,
}

function speakBeats(beats: Beat[], onDone: () => void) {
  if (!('speechSynthesis' in window)) { onDone(); return () => {} }
  window.speechSynthesis.cancel()
  let cancelled = false

  const run = async () => {
    for (const beat of beats) {
      if (cancelled) break
      await new Promise<void>((resolve) => {
        const utt = new SpeechSynthesisUtterance(beat.text)
        utt.lang = 'vi-VN'
        utt.rate = 0.95
        utt.onend = () => resolve()
        utt.onerror = () => resolve()
        window.speechSynthesis.speak(utt)
      })
      if (cancelled) break
      const pause = PAUSE_MS[beat.pause_after ?? 'short'] ?? 150
      if (pause > 0) await new Promise((r) => setTimeout(r, pause))
    }
    if (!cancelled) onDone()
  }
  void run()
  return () => { cancelled = true; window.speechSynthesis.cancel() }
}

const EXAMPLE_BODY = {
  id: '00000000-0000-0000-0000-000000000001',
  version: '1.0.0',
  campaign_id: '00000000-0000-0000-0000-000000000010',
  direction: 'inbound',
  voice_profile: 'linh_clone_v1',
  entry_step: 'greeting',
  steps: [
    {
      id: 'greeting',
      type: 'speak_listen',
      variants: [
        {
          id: 'v1',
          beats: [{ text: 'Xin chào,', pause_after: 'breath' }, { text: 'Hôm nay tôi có thể hỗ trợ gì cho bạn ạ?', pause_after: 'turn' }],
        },
      ],
      reprompt_variants: [
        { id: 'r1', beats: [{ text: 'Bạn cần hỗ trợ gì không ạ?', pause_after: 'turn' }] },
        { id: 'r2', beats: [{ text: 'Tôi vẫn đang nghe ạ.', pause_after: 'turn' }] },
        { id: 'r3', beats: [{ text: 'Tôi chuyển bạn sang nhân viên trực tiếp nhé ạ.', pause_after: 'turn' }] },
      ],
      transitions: [{ when: "intent == 'done'", goto: 'farewell' }],
      fallback_goto: 'farewell',
      max_no_match: 3,
    },
    {
      id: 'farewell',
      type: 'speak',
      variants: [{ id: 'v1', beats: [{ text: 'Cảm ơn bạn đã gọi. Chúc bạn sức khỏe ạ.', pause_after: 'long' }] }],
    },
  ],
}

export default function NewVersionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()
  const [version, setVersion] = useState('1.0.0')
  const [bodyText, setBodyText] = useState(JSON.stringify(EXAMPLE_BODY, null, 2))
  const [lintResult, setLintResult] = useState<LintResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const stopRef = useRef<(() => void) | null>(null)

  function parseBody(): Record<string, unknown> | null {
    try {
      setParseError(null)
      return JSON.parse(bodyText) as Record<string, unknown>
    } catch (e) {
      setParseError((e as Error).message)
      return null
    }
  }

  async function handleValidate() {
    const body = parseBody()
    if (!body) return
    setValidating(true)
    setLintResult(null)
    try {
      const res = await fetch('/api/v1/scripts/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
      })
      const result = (await res.json()) as LintResult
      setLintResult(result)
    } catch {
      setParseError('Không thể kết nối tới server để validate')
    } finally {
      setValidating(false)
    }
  }

  async function handleSave() {
    const body = parseBody()
    if (!body) return
    setSaving(true)
    try {
      const res = await fetch(`/api/v1/scripts/${id}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version, body }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        setParseError(err.message ?? 'Lỗi lưu version')
        return
      }
      router.push(`/scripts/${id}`)
    } catch {
      setParseError('Không thể kết nối tới server')
    } finally {
      setSaving(false)
    }
  }

  function handlePreview() {
    if (playing) {
      stopRef.current?.()
      setPlaying(false)
      return
    }
    const body = parseBody()
    if (!body) return
    const beats = extractBeats(body as ScriptBody)
    if (beats.length === 0) { setParseError('Không tìm thấy beat nào để phát'); return }
    setPlaying(true)
    stopRef.current = speakBeats(beats, () => setPlaying(false))
  }

  const canSave = lintResult?.valid === true && !parseError

  return (
    <div className="p-8 max-w-4xl mx-auto">
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
        Script body sẽ được validate theo lint rules L001–L008 trước khi lưu.
      </p>

      <div className="space-y-6">
        {/* Version input */}
        <div>
          <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
            Version
          </label>
          <input
            type="text"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="1.0.0"
            className="input max-w-xs"
          />
          <p className="text-xs text-[var(--color-text-muted)] mt-1.5">Semver: MAJOR.MINOR.PATCH</p>
        </div>

        {/* JSON body */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-sm font-medium text-[var(--color-text)]">Script Body (JSON)</label>
            <span className="text-xs text-[var(--color-text-muted)]">CallScript v0.1</span>
          </div>
          <textarea
            value={bodyText}
            onChange={(e) => {
              setBodyText(e.target.value)
              setLintResult(null)
              setParseError(null)
            }}
            rows={20}
            className="input font-mono text-xs leading-relaxed resize-y"
            spellCheck={false}
          />
          {parseError && (
            <p className="mt-1.5 text-xs text-[var(--color-danger)]">⚠ {parseError}</p>
          )}
        </div>

        {/* Lint result */}
        {lintResult && <LintResultPanel result={lintResult} />}

        {/* Actions */}
        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={() => void handleValidate()}
            disabled={validating}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-[var(--color-border)] text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)] disabled:opacity-50 transition-colors"
          >
            {validating && <Loader2 className="w-4 h-4 animate-spin" />}
            Validate
          </button>
          <button
            type="button"
            onClick={handlePreview}
            className={[
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors',
              playing
                ? 'border-[var(--color-accent)] bg-[oklch(96%_0.03_250)] text-[var(--color-accent)]'
                : 'border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-overlay)]',
            ].join(' ')}
          >
            {playing ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            {playing ? 'Dừng' : 'Nghe thử'}
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving || !canSave}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Lưu Draft
          </button>
        </div>
      </div>
    </div>
  )
}

function LintResultPanel({ result }: { result: LintResult }) {
  return (
    <div
      className={[
        'rounded-xl border p-5 space-y-3',
        result.valid
          ? 'bg-[oklch(97%_0.04_145)] border-[oklch(85%_0.09_145)]'
          : 'bg-[oklch(97%_0.04_27)] border-[oklch(85%_0.08_27)]',
      ].join(' ')}
    >
      <div className="flex items-center gap-2">
        {result.valid ? (
          <CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" />
        ) : (
          <XCircle className="w-4 h-4 text-[var(--color-danger)]" />
        )}
        <span className="text-sm font-semibold text-[var(--color-text)]">
          {result.valid ? 'Script hợp lệ — có thể lưu' : `${result.errors.length} lỗi cần sửa`}
        </span>
      </div>

      {result.errors.map((e) => (
        <div key={`${e.code}-${e.field}`} className="flex gap-2 text-sm">
          <span className="shrink-0 font-mono text-xs font-bold text-[var(--color-danger)] pt-0.5">
            {e.code}
          </span>
          <div>
            <p className="text-[var(--color-text)]">{e.message}</p>
            {e.field && <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{e.field}</p>}
          </div>
        </div>
      ))}

      {result.warnings.map((w) => (
        <div key={`${w.code}-${w.field}`} className="flex gap-2 text-sm">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-[var(--color-warning)] mt-0.5" />
          <span className="font-mono text-xs font-bold text-[var(--color-warning)] shrink-0">
            {w.code}
          </span>
          <p className="text-[var(--color-text-muted)]">{w.message}</p>
        </div>
      ))}
    </div>
  )
}
