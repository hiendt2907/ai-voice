'use client'

import { useState, useEffect } from 'react'
import { Bell, Eye, EyeOff, Send, Globe } from 'lucide-react'
import { Field, SelectField, NumberField } from './Field'
import { SectionFooter, SectionSkeleton, StatusDot, Meta } from './CloudFoneSection'

interface NotifySettings {
  platform: string
  teamsWebhookUrl: string
  telegramBotToken: string
  telegramGroupId: string
  questionTimeoutSeconds: number
  callbackDelayMinutes: number
  updatedBy: string | null
  updatedAt: string
}

type SaveStatus = 'idle' | 'saving' | 'ok' | 'error'

const PLATFORM_OPTIONS = [
  { value: 'none', label: 'Tắt thông báo' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'teams', label: 'Microsoft Teams' },
  { value: 'both', label: 'Telegram + Teams' },
]

export function NotifySection() {
  const [form, setForm] = useState<NotifySettings>({
    platform: 'telegram', teamsWebhookUrl: '', telegramBotToken: '', telegramGroupId: '',
    questionTimeoutSeconds: 300, callbackDelayMinutes: 10, updatedBy: null, updatedAt: '',
  })
  const [meta, setMeta] = useState<Pick<NotifySettings, 'updatedBy' | 'updatedAt'> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [showToken, setShowToken] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/settings/notify')
        if (res.ok) {
          const data = (await res.json()) as NotifySettings
          setForm(data)
          setMeta({ updatedBy: data.updatedBy, updatedAt: data.updatedAt })
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function set<K extends keyof NotifySettings>(field: K, value: NotifySettings[K]) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaveStatus('idle')
  }

  async function handleSave() {
    setSaveStatus('saving')
    setErrorMsg('')
    try {
      const res = await fetch('/api/v1/settings/notify', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: form.platform,
          teamsWebhookUrl: form.teamsWebhookUrl ?? '',
          telegramBotToken: form.telegramBotToken ?? '',
          telegramGroupId: form.telegramGroupId ?? '',
          questionTimeoutSeconds: form.questionTimeoutSeconds,
          callbackDelayMinutes: form.callbackDelayMinutes,
        }),
      })
      if (!res.ok) {
        const err = (await res.json()) as { message?: string }
        throw new Error(err.message ?? `HTTP ${res.status}`)
      }
      const saved = (await res.json()) as NotifySettings
      setMeta({ updatedBy: saved.updatedBy, updatedAt: saved.updatedAt })
      setSaveStatus('ok')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (e) {
      setErrorMsg((e as Error).message)
      setSaveStatus('error')
    }
  }

  const telegramOk = !!form.telegramBotToken && form.telegramBotToken !== '' && !!form.telegramGroupId
  const teamsOk = !!form.teamsWebhookUrl && form.teamsWebhookUrl !== ''
  const isConfigured = form.platform !== 'none' && (
    (form.platform === 'telegram' && telegramOk) ||
    (form.platform === 'teams' && teamsOk) ||
    (form.platform === 'both' && telegramOk && teamsOk)
  )

  const activePlatformLabel = PLATFORM_OPTIONS.find((o) => o.value === form.platform)?.label ?? form.platform

  if (loading) return <SectionSkeleton />

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-overlay)]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[oklch(96%_0.03_50)] flex items-center justify-center">
            <Bell className="w-4 h-4 text-[oklch(55%_0.18_50)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--color-text)]">Thông báo</p>
            <p className="text-xs text-[var(--color-text-muted)]">Escalate câu hỏi chưa có đáp án qua chat</p>
          </div>
        </div>
        <StatusDot ok={isConfigured} label={isConfigured ? activePlatformLabel : 'Chưa cấu hình'} />
      </div>

      <div className="px-6 py-6 space-y-6">
        <SelectField
          label="Kênh thông báo"
          hint="Chọn nền tảng nhận thông báo khi AI không trả lời được"
          value={form.platform}
          onChange={(v) => set('platform', v)}
          options={PLATFORM_OPTIONS}
        />

        {/* ── Telegram ──────────────────────────────── */}
        <div className={[
          'rounded-xl border p-4 space-y-4 transition-opacity',
          form.platform === 'none' ? 'opacity-40 pointer-events-none' : '',
          form.platform === 'teams' ? 'opacity-40 pointer-events-none' : '',
        ].join(' ')}>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded flex items-center justify-center bg-[oklch(92%_0.06_240)]">
              <Send className="w-3.5 h-3.5 text-[oklch(50%_0.18_240)]" />
            </div>
            <p className="text-sm font-semibold text-[var(--color-text)]">Telegram Bot</p>
            {telegramOk && (
              <span className="ml-auto text-xs text-[oklch(55%_0.16_145)] bg-[oklch(95%_0.04_145)] px-2 py-0.5 rounded-full">Đã cấu hình</span>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
              Bot Token
            </label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={form.telegramBotToken ?? ''}
                onChange={(e) => set('telegramBotToken', e.target.value)}
                placeholder="1234567890:ABCdefGHIjklMNOpqrSTUvwxyz"
                className="input pr-10"
              />
              <button
                type="button"
                onClick={() => setShowToken((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              Lấy từ <strong>@BotFather</strong> trên Telegram → /newbot → copy token
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
              Chat ID / Group ID
            </label>
            <input
              type="text"
              value={form.telegramGroupId ?? ''}
              onChange={(e) => set('telegramGroupId', e.target.value)}
              placeholder="-1001234567890"
              className="input"
            />
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              Group: thêm bot vào nhóm → gửi tin → gọi{' '}
              <code className="bg-[var(--color-surface)] px-1 rounded">getUpdates</code>{' '}
              để lấy ID (số âm, bắt đầu bằng -100)
            </p>
          </div>
        </div>

        {/* ── Microsoft Teams ───────────────────────── */}
        <div className={[
          'rounded-xl border p-4 space-y-4 transition-opacity',
          form.platform === 'none' ? 'opacity-40 pointer-events-none' : '',
          form.platform === 'telegram' ? 'opacity-40 pointer-events-none' : '',
        ].join(' ')}>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded flex items-center justify-center bg-[oklch(92%_0.06_270)]">
              <Globe className="w-3.5 h-3.5 text-[oklch(50%_0.18_270)]" />
            </div>
            <p className="text-sm font-semibold text-[var(--color-text)]">Microsoft Teams</p>
            {teamsOk && (
              <span className="ml-auto text-xs text-[oklch(55%_0.16_145)] bg-[oklch(95%_0.04_145)] px-2 py-0.5 rounded-full">Đã cấu hình</span>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1.5">
              Incoming Webhook URL
            </label>
            <input
              type="url"
              value={form.teamsWebhookUrl ?? ''}
              onChange={(e) => set('teamsWebhookUrl', e.target.value)}
              placeholder="https://xxx.webhook.office.com/webhookb2/..."
              className="input"
            />
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              Tạo tại Teams → kênh mong muốn → <strong>Connectors</strong> → <strong>Incoming Webhook</strong> → Configure → copy URL
            </p>
          </div>
        </div>

        {/* ── Timing ────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-4">
          <NumberField
            label="Question Timeout (giây)"
            hint="Chờ nhân viên trả lời bao lâu trước khi fallback"
            value={form.questionTimeoutSeconds}
            onChange={(v) => set('questionTimeoutSeconds', v)}
            min={30}
            step={30}
          />
          <NumberField
            label="Callback Delay (phút)"
            hint="Delay trước khi yêu cầu callback với khách"
            value={form.callbackDelayMinutes}
            onChange={(v) => set('callbackDelayMinutes', v)}
            min={1}
          />
        </div>

        <Meta updatedAt={meta?.updatedAt} updatedBy={meta?.updatedBy} />
      </div>

      <SectionFooter saveStatus={saveStatus} errorMsg={errorMsg} onSave={() => void handleSave()} />
    </div>
  )
}
