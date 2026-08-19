import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('tts_settings')
export class TtsSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: 'edge-tts' })
  engine: string

  @Column({ default: 'vi-VN-HoaiMyNeural' })
  voice: string

  @Column({ default: 8000 })
  sampleRate: number

  @Column({ type: 'float', default: 1.0 })
  speedFactor: number

  // ElevenLabs-specific fields
  @Column({ type: 'varchar', nullable: true, default: null })
  elevenlabsApiKey: string | null

  @Column({ default: 'hpp4J3VqNfWAUOO0d1Us' })
  elevenlabsVoiceId: string

  @Column({ default: 'eleven_turbo_v2_5' })
  elevenlabsModelId: string

  @Column({ type: 'float', default: 0.6 })
  elevenlabsStability: number

  @Column({ type: 'float', default: 0.75 })
  elevenlabsSimilarityBoost: number

  @Column({ type: 'float', default: 0.3 })
  elevenlabsStyleExaggeration: number

  @Column({ default: true })
  elevenlabsUseSpeakerBoost: boolean

  @Column({ type: 'simple-json', default: () => `'["local","edge-tts","elevenlabs"]'` })
  engineFallbackOrder: string[]

  @Column({ default: 0 })
  elevenlabsDailyCharQuota: number

  @Column({ default: 3 })
  circuitBreakerFailures: number

  @Column({ default: 300 })
  circuitBreakerResetSecs: number

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
