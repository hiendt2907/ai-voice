'use client'

import { use, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Star, CheckCircle2, Loader2 } from 'lucide-react'

export default function CallDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [score, setScore] = useState<number | null>(null)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  async function submitScore() {
    if (score === null) return
    setSubmitting(true)
    try {
      await fetch(`/api/v1/calls/${id}/qa-scores`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ score, notes: notes || undefined }),
      })
      setSubmitted(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Link
        href="/calls"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Cuộc gọi
      </Link>

      <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight mb-1">
        Chi tiết cuộc gọi
      </h1>
      <p className="text-xs font-mono text-[var(--color-text-muted)] mb-8">{id}</p>

      {/* QA Scoring Panel */}
      <section className="rounded-xl border border-[var(--color-border)] bg-white p-6 mb-6">
        <h2 className="text-sm font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
          <Star className="w-4 h-4 text-[var(--color-warning)]" />
          QA Scoring
        </h2>

        {submitted ? (
          <div className="flex items-center gap-2 text-sm text-[var(--color-success)]">
            <CheckCircle2 className="w-4 h-4" />
            Đã gửi đánh giá thành công
          </div>
        ) : (
          <div className="space-y-4">
            {/* Star rating */}
            <div>
              <p className="text-xs font-medium text-[var(--color-text-muted)] mb-2">Điểm (0–5)</p>
              <div className="flex gap-1.5">
                {[1, 2, 3, 4, 5].map((s) => (
                  <button
                    key={s}
                    onClick={() => setScore(s)}
                    className={[
                      'w-9 h-9 rounded-lg border text-sm font-semibold transition-all duration-[var(--duration-fast)]',
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

            {/* Notes */}
            <div>
              <p className="text-xs font-medium text-[var(--color-text-muted)] mb-2">Ghi chú (không bắt buộc)</p>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                placeholder="Nhận xét về cuộc gọi..."
                className="input resize-none"
              />
            </div>

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

      {/* Transcript placeholder */}
      <section className="rounded-xl border border-[var(--color-border)] bg-white p-6">
        <h2 className="text-sm font-semibold text-[var(--color-text)] mb-4">Transcript</h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          Transcript sẽ được tải từ API. Kết nối Voice Worker để xem dữ liệu thực.
        </p>
      </section>
    </div>
  )
}
