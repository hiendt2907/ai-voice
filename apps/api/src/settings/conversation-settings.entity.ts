import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('conversation_settings')
export class ConversationSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: false })
  enabled: boolean

  @Column({ default: 'qwen2.5:3b' })
  ollamaModel: string

  @Column({ type: 'text', default: '' })
  systemPrompt: string

  @Column({ default: 5 })
  maxHistoryTurns: number

  @Column({ type: 'float', default: 0.3 })
  temperature: number

  @Column({ default: false })
  sentimentEnabled: boolean

  @Column({ default: true })
  kbGroundingEnabled: boolean

  @Column({ default: 30 })
  sentenceSplitMinChars: number

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
