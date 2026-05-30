import {
  Entity,
  PrimaryColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
} from 'typeorm'

@Entity('voice_profiles')
export class VoiceProfile {
  @PrimaryColumn()
  id: string

  @Column()
  displayName: string

  @Column({ default: 'male' })
  gender: string

  @Column({ type: 'varchar', nullable: true })
  region: string | null

  @Column({ default: 'qwen-tts' })
  ttsEngine: string

  @Column()
  ttsVoiceId: string

  @Column({ type: 'varchar', nullable: true })
  elevenlabsVoiceId: string | null

  @Column('int', { default: 8000 })
  sampleRate: number

  @Column({ type: 'float', default: 0.6 })
  stabilityFactor: number

  @Column({ type: 'float', default: 0.75 })
  similarityBoost: number

  @Column({ type: 'float', default: 0.3 })
  styleExaggeration: number

  @Column({ default: true })
  useSpeakerBoost: boolean

  @Column({ type: 'jsonb', nullable: true })
  prosodyPreset: Record<string, unknown> | null

  @Column({ type: 'simple-array', nullable: true })
  customFillerPool: string[] | null

  @Column({ default: true })
  isActive: boolean

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
