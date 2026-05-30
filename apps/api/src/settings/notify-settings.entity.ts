import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('notify_settings')
export class NotifySettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: 'telegram' })
  platform: string

  @Column({ default: '' })
  teamsWebhookUrl: string

  @Column({ default: '' })
  telegramBotToken: string

  @Column({ default: '' })
  telegramGroupId: string

  @Column({ default: 300 })
  questionTimeoutSeconds: number

  @Column({ default: 10 })
  callbackDelayMinutes: number

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
