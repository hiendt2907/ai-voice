'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Search, Play } from 'lucide-react'

interface SearchResult {
  score: number
  article_id: string
  title: string
  answer_female: string
  answer_male: string
  answer_unknown: string
  tags: string[]
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    score >= 0.85
      ? 'bg-[oklch(95%_0.06_145)] text-[oklch(32%_0.14_145)]'
      : score >= 0.7
      ? 'bg-[oklch(96%_0.08_85)] text-[oklch(40%_0.14_85)]'
      : 'bg-[oklch(97%_0.04_27)] text-[oklch(40%_0.16_27)]'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold font-mono ${color}`}>
      {pct}%
    </span>
  )
}

export default function KbTestPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSearch() {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/v1/knowledge/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), limit: 3 }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResults((await res.json()) as SearchResult[])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function playAnswer(text: string) {
    // Simple TTS preview via browser speech synthesis fallback
    if ('speechSynthesis' in window) {
      const utt = new SpeechSynthesisUtterance(text)
      utt.lang = 'vi-VN'
      speechSynthesis.cancel()
      speechSynthesis.speak(utt)
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-6">
        <Link
          href="/knowledge"
          className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors mb-4"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Về Knowledge Base
        </Link>
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Test Knowledge Base</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Nhập câu hỏi để kiểm tra xem hệ thống RAG sẽ trả lời như thế nào
        </p>
      </div>

      {/* Search box */}
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void handleSearch()}
          placeholder="Ví dụ: Chi phí siêu âm thai là bao nhiêu?"
          className="input flex-1"
        />
        <button
          type="button"
          onClick={() => void handleSearch()}
          disabled={loading || !query.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          <Search className="w-4 h-4" />
          {loading ? 'Đang tìm...' : 'Tìm kiếm'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-[oklch(97%_0.04_27)] border border-[oklch(88%_0.06_27)]">
          <p className="text-sm text-[oklch(40%_0.16_27)]">Lỗi: {error}</p>
        </div>
      )}

      {/* Results */}
      {results !== null && (
        <div className="space-y-4">
          <p className="text-xs text-[var(--color-text-muted)]">
            Top {results.length} kết quả — không áp dụng ngưỡng confidence
          </p>
          {results.length === 0 && (
            <div className="p-8 text-center rounded-xl border border-dashed border-[var(--color-border)]">
              <p className="text-sm text-[var(--color-text-muted)]">Không có kết quả (KB chưa được embed?)</p>
            </div>
          )}
          {results.map((r, i) => (
            <div key={r.article_id} className="rounded-xl border border-[var(--color-border)] bg-white overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
                <span className="text-xs text-[var(--color-text-muted)] font-medium">#{i + 1}</span>
                <ScoreBadge score={r.score} />
                <p className="text-sm font-semibold text-[var(--color-text)] flex-1">{r.title}</p>
                {r.tags.length > 0 && (
                  <div className="flex gap-1">
                    {r.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="text-[10px] px-1.5 py-0.5 bg-[oklch(93%_0.04_250)] text-[oklch(40%_0.12_250)] rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="px-5 py-4 space-y-3">
                <AnswerRow label="Nữ" text={r.answer_female} onPlay={() => void playAnswer(r.answer_female)} />
                <AnswerRow label="Nam" text={r.answer_male} onPlay={() => void playAnswer(r.answer_male)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AnswerRow({ label, text, onPlay }: { label: string; text: string; onPlay: () => void }) {
  return (
    <div className="flex items-start gap-3">
      <span className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[oklch(93%_0.04_250)] text-[oklch(40%_0.12_250)] mt-0.5">
        {label}
      </span>
      <p className="text-sm text-[var(--color-text)] flex-1 leading-relaxed">{text}</p>
      <button
        type="button"
        onClick={onPlay}
        title={`Nghe giọng ${label}`}
        className="shrink-0 p-1.5 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:bg-[var(--color-surface-overlay)] transition-colors"
      >
        <Play className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
