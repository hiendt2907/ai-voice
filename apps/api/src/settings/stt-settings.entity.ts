import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('stt_settings')
export class SttSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: 'faster_whisper' })
  engine: string

  @Column({ default: 'small' })
  modelSize: string

  @Column({ default: 'cpu' })
  device: string

  @Column({ default: 'int8' })
  computeType: string

  @Column({ default: 'vi' })
  language: string

  @Column({ default: 400 })
  endOfUtteranceSilenceMs: number

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
