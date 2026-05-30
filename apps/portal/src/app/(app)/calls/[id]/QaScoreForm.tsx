'use client'

import { useState } from 'react'
import { Star, CheckCircle2, Loader2 } from 'lucide-react'

interface QaScore {
  id: string
  score: number
  notes: string | null
  scoredBy: string
  createdAt: string
}

interface Props {
  callId: string
  existingScores: QaScore[]
}

export function QaScoreForm({ callId, existingScores }: Props) {
  const [score, setScore] = useState<number | null>(null)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  async function submitScore() {
    if (score === null) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`/api/v1/calls/${callId}/qa-scores`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ score, notes: notes || undefined }),
      })
      if (!res.ok) {
        const data = await res.json() as { message?: string }
        setError(data.message ?? 'Lỗi khi gửi đánh giá')
        return
      }
      setSubmitted(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-white p-6">
      <h2 className="text-sm font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
        <Star className="w-4 h-4 text-[var(--color-warning)]" />
        QA Scoring
        {existingScores.length > 0 && (
          <span className="text-xs font-normal text-[var(--color-text-muted)]">
            — {existingScores.length} đánh giá trước
          </span>
        )}
      </h2>

      {existingScores.length > 0 && (
        <div className="mb-4 space-y-2">
          {existingScores.map((s) => (
            <div key={s.id} className="flex items-center gap-3 p-2.5 rounded-lg bg-[var(--color-surface-overlay)]">
              <span className="text-sm font-bold text-[var(--color-warning)]">{s.score}/5</span>
              <span className="text-xs text-[var(--color-text-muted)]">{s.notes ?? 'Không có ghi chú'}</span>
            </div>
          ))}
        </div>
      )}

      {submitted ? (
        <div className="flex items-center gap-2 text-sm text-[var(--color-success)]">
          <CheckCircle2 className="w-4 h-4" />
          Đã gửi đánh giá thành công
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <p className="text-xs font-medium text-[var(--color-text-muted)] mb-2">Điểm (1–5)</p>
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  onClick={() => setScore(s)}
                  className={[
                    'w-9 h-9 rounded-lg border text-sm font-semibold transition-all',
                    score === s
                      ? 'bg-[var(--color-warning)] border-[var(--color-warning)] text-white'
                      : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-warning)] hover:text-[var(--color-warning)]',
                  ].join(' ')}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-medium text-[var(--color-text-muted)] mb-2">Ghi chú</p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Nhận xét về cuộc gọi..."
              className="input resize-none"
            />
          </div>
          {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}
          <button
            onClick={() => void submitScore()}
            disabled={score === null || submitting}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Gửi đánh giá
          </button>
        </div>
      )}
    </section>
  )
}
