/**
 * Glassbox view of one caller turn — the decision chain behind the reply.
 *
 * Renders what services/voice/obs/turn_trace.py recorded: what STT heard,
 * which NLU tier resolved it, whether RAG grounded the answer, whether a
 * guardrail blocked it, and where the FSM moved. The point is that a reader
 * can tell *why* the agent said what it said without reading pod logs.
 */

export interface TurnTraceData {
  turn?: number
  trace_id?: string
  stt?: { text?: string; confidence?: number | null; engine?: string; ms?: number | null }
  nlu?: {
    tier?: string
    intent?: string | null
    confidence?: number | null
    llm_used?: boolean
    ms?: number | null
  }
  rag?: {
    hit?: boolean
    article_title?: string | null
    score?: number | null
    ms?: number | null
  }
  guardrail?: { blocked?: boolean; reason?: string | null }
  llm?: {
    model?: string | null
    prompt_tokens?: number | null
    completion_tokens?: number | null
    refused?: boolean
    ms?: number | null
  }
  routing?: {
    step_from?: string
    step_to?: string
    slots_new?: Record<string, string>
    escalated?: boolean
  }
  agent?: { text?: string; tts_engine?: string; ttfa_ms?: number | null }
  total_ms?: number | null
}

/** Confidence colouring: these thresholds mirror the NLU tiers — at or above
 * 0.8 the resolver is "confident" and the FSM transitions on it, 0.6-0.8 is
 * the clarify band, below that it is effectively a miss. */
function confidenceTone(value?: number | null): string {
  if (value == null) return 'text-[var(--color-text-muted)]'
  if (value >= 0.8) return 'text-emerald-600 dark:text-emerald-400'
  if (value >= 0.6) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}

function ms(value?: number | null): string {
  return value == null ? '—' : `${Math.round(value)}ms`
}

function Stage({
  label,
  tone = 'default',
  children,
}: {
  label: string
  tone?: 'default' | 'warn' | 'danger' | 'ok'
  children: React.ReactNode
}) {
  const toneClass =
    tone === 'danger'
      ? 'border-red-300 dark:border-red-800'
      : tone === 'warn'
        ? 'border-amber-300 dark:border-amber-800'
        : tone === 'ok'
          ? 'border-emerald-300 dark:border-emerald-800'
          : 'border-[var(--color-border)]'

  return (
    <div className={`rounded-lg border ${toneClass} bg-[var(--color-surface)] p-3`}>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
        {label}
      </div>
      <div className="text-sm text-[var(--color-text)]">{children}</div>
    </div>
  )
}

export function TurnTrace({ data }: { data: TurnTraceData }) {
  const { stt, nlu, rag, guardrail, llm, routing, agent } = data
  const slots = routing?.slots_new ?? {}
  const slotKeys = Object.keys(slots)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-muted)]">
        <span className="font-semibold text-[var(--color-text)]">Lượt {data.turn ?? '?'}</span>
        <span>tổng {ms(data.total_ms)}</span>
        {/* llm_used is the number to watch: every true here is a ~2s cloud
            round-trip that a better NLU example would have avoided. */}
        {nlu?.llm_used ? (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            có gọi LLM
          </span>
        ) : (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
            vector NLU
          </span>
        )}
        {routing?.escalated && (
          <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-800 dark:bg-blue-950 dark:text-blue-300">
            chuyển nhân viên
          </span>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <Stage label={`Nghe được · ${stt?.engine || '—'}`}>
          <div className="font-medium">{stt?.text || <em>(trống)</em>}</div>
          <div className="mt-1 text-xs">
            <span className={confidenceTone(stt?.confidence)}>
              conf {stt?.confidence?.toFixed(2) ?? '—'}
            </span>
            <span className="ml-2 text-[var(--color-text-muted)]">{ms(stt?.ms)}</span>
          </div>
        </Stage>

        <Stage label={`Hiểu · ${nlu?.tier || '—'}`}>
          <div className="font-medium">{nlu?.intent || <em>không khớp intent nào</em>}</div>
          <div className="mt-1 text-xs">
            <span className={confidenceTone(nlu?.confidence)}>
              {nlu?.confidence?.toFixed(3) ?? '—'}
            </span>
            <span className="ml-2 text-[var(--color-text-muted)]">{ms(nlu?.ms)}</span>
          </div>
        </Stage>

        <Stage label="Tra cứu KB" tone={rag?.hit ? 'ok' : 'default'}>
          {rag?.hit ? (
            <>
              <div className="font-medium">{rag.article_title || '(không rõ tiêu đề)'}</div>
              <div className="mt-1 text-xs">
                <span className={confidenceTone(rag.score)}>{rag.score?.toFixed(3) ?? '—'}</span>
                <span className="ml-2 text-[var(--color-text-muted)]">{ms(rag.ms)}</span>
              </div>
            </>
          ) : (
            <em className="text-[var(--color-text-muted)]">không tra KB</em>
          )}
        </Stage>

        <Stage
          label="An toàn"
          tone={guardrail?.blocked ? 'danger' : llm?.refused ? 'warn' : 'default'}
        >
          {guardrail?.blocked ? (
            <div className="text-red-600 dark:text-red-400">
              Chặn: {guardrail.reason || 'chủ đề cấm'}
            </div>
          ) : llm?.refused ? (
            <div className="text-amber-600 dark:text-amber-400">
              Model từ chối — không đủ căn cứ
            </div>
          ) : (
            <em className="text-[var(--color-text-muted)]">không chặn</em>
          )}
          {llm?.model && (
            <div className="mt-1 text-xs text-[var(--color-text-muted)]">
              {llm.model}
              {llm.prompt_tokens != null &&
                ` · ${llm.prompt_tokens}+${llm.completion_tokens ?? 0} tokens`}
            </div>
          )}
        </Stage>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
        <span className="rounded bg-[var(--color-surface-alt)] px-2 py-1 font-mono">
          {routing?.step_from || '?'} → {routing?.step_to || '?'}
        </span>
        {slotKeys.length > 0 && (
          <span>
            slot mới:{' '}
            {slotKeys.map((k) => (
              <span key={k} className="ml-1 font-mono text-[var(--color-text)]">
                {k}={slots[k]}
              </span>
            ))}
          </span>
        )}
        {agent?.tts_engine && (
          <span>
            TTS {agent.tts_engine} · TTFA {ms(agent.ttfa_ms)}
          </span>
        )}
      </div>
    </div>
  )
}
