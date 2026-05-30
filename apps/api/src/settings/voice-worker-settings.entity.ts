import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('voice_worker_settings')
export class VoiceWorkerSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: 'http://localhost:8000' })
  internalUrl: string

  @Column({ default: 10 })
  maxConcurrentSessions: number

  @Column({ default: 3600 })
  sessionCacheTtlSeconds: number

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
