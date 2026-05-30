import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  OneToOne,
  JoinColumn,
} from 'typeorm'
import { CallSession } from './call-session.entity'

@Entity('call_metrics')
export class CallMetrics {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid', { unique: true })
  callSessionId: string

  @OneToOne(() => CallSession, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'callSessionId' })
  callSession: CallSession

  @Column({ type: 'int', nullable: true })
  ttfaMs: number | null

  @Column({ type: 'int', nullable: true })
  avgTurnLatencyMs: number | null

  @Column('int', { default: 0 })
  bargeInCount: number

  @Column('int', { default: 0 })
  noMatchCount: number

  @Column('int', { default: 0 })
  repromptCount: number

  @Column({ type: 'int', nullable: true })
  stepCount: number | null

  @CreateDateColumn()
  createdAt: Date
}
