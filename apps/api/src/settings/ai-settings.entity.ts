import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('ai_settings')
export class AiSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: 'http://localhost:11434/v1' })
  ollamaBaseUrl: string

  @Column({ default: 'qwen2.5:latest' })
  ollamaModel: string

  @Column({ default: 800 })
  nluTimeoutMs: number

  @Column({ default: 2000 })
  responseTimeoutMs: number

  @Column({ default: true })
  fallbackToSubstring: boolean

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
