'use client'

import { useState } from 'react'
import { CloudFoneSection } from './CloudFoneSection'
import { AiSection } from './AiSection'
import { SttSection } from './SttSection'
import { TtsSection } from './TtsSection'
import { NotifySection } from './NotifySection'
import { VoiceWorkerSection } from './VoiceWorkerSection'
import { DoctorCheckSection } from './DoctorCheckSection'
import { VoiceProfilesSection } from './VoiceProfilesSection'
import { ConversationSection } from './ConversationSection'

type Tab = 'cloudfone' | 'doctorcheck' | 'ai' | 'conversation' | 'stt' | 'tts' | 'voices' | 'notify' | 'voice-worker'

const TABS: { id: Tab; label: string }[] = [
  { id: 'cloudfone', label: 'CloudFone' },
  { id: 'doctorcheck', label: 'DoctorCheck' },
  { id: 'ai', label: 'AI / LLM' },
  { id: 'conversation', label: 'Conversation' },
  { id: 'stt', label: 'STT' },
  { id: 'tts', label: 'TTS' },
  { id: 'voices', label: 'Voice Profiles' },
  { id: 'notify', label: 'Thông báo' },
  { id: 'voice-worker', label: 'Voice Worker' },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('cloudfone')

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--color-text)] tracking-tight">Cài đặt</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Cấu hình hệ thống AI call — thay đổi áp dụng sau khi reload voice worker
        </p>
      </div>

      {/* Tab navigation */}
      <div className="flex gap-1 mb-6 p-1 bg-[var(--color-surface-overlay)] rounded-xl border border-[var(--color-border)] overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={[
              'flex-shrink-0 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              activeTab === tab.id
                ? 'bg-white text-[var(--color-text)] shadow-sm border border-[var(--color-border)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-white/50',
            ].join(' ')}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Section content */}
      {activeTab === 'cloudfone' && <CloudFoneSection />}
      {activeTab === 'doctorcheck' && <DoctorCheckSection />}
      {activeTab === 'ai' && <AiSection />}
      {activeTab === 'conversation' && <ConversationSection />}
      {activeTab === 'stt' && <SttSection />}
      {activeTab === 'tts' && <TtsSection />}
      {activeTab === 'voices' && <VoiceProfilesSection />}
      {activeTab === 'notify' && <NotifySection />}
      {activeTab === 'voice-worker' && <VoiceWorkerSection />}
    </div>
  )
}
