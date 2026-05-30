import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  Unique,
} from 'typeorm'

@Entity('analytics_daily')
@Unique(['date', 'campaignId'])
export class AnalyticsDaily {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column({ type: 'date' })
  date: string

  @Column({ type: 'uuid', nullable: true })
  campaignId: string | null

  @Column('int', { default: 0 })
  totalCalls: number

  @Column('int', { default: 0 })
  completedCalls: number

  @Column('int', { default: 0 })
  handoffCalls: number

  @Column('int', { default: 0 })
  errorCalls: number

  @Column({ type: 'decimal', precision: 10, scale: 2, default: 0 })
  avgDurationSeconds: number

  @Column({ type: 'decimal', precision: 4, scale: 2, nullable: true })
  avgQaScore: number | null

  @Column({ type: 'decimal', precision: 5, scale: 4, default: 0 })
  containmentRate: number

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
