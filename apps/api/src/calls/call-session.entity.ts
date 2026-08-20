import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  Index,
} from 'typeorm'

export type CallStatus = 'active' | 'completed' | 'handoff' | 'error'

@Entity('call_sessions')
@Index(['campaignId', 'createdAt'])
@Index(['status', 'createdAt'])
export class CallSession {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid', { nullable: true })
  campaignId: string | null

  @Column('uuid', { nullable: true })
  scriptVersionId: string | null

  @Column({ unique: true })
  sessionId: string

  @Column({ type: 'enum', enum: ['inbound', 'outbound'], default: 'inbound' })
  direction: 'inbound' | 'outbound'

  @Column({ type: 'varchar', nullable: true })
  callerNumberMasked: string | null

  @Column({
    type: 'enum',
    enum: ['active', 'completed', 'handoff', 'error'],
    default: 'active',
  })
  status: CallStatus

  @Column({ type: 'jsonb', nullable: true })
  transcript: Record<string, unknown>[] | null

  @Column({ type: 'jsonb', nullable: true })
  slots: Record<string, string> | null

  @Column({ type: 'varchar', nullable: true })
  finalStepId: string | null

  /**
   * W3C trace id (32 hex chars) shared by every hop of this call — softphone,
   * voice worker, this API. Minted by the SIP bridge when the call is
   * answered; use it to open the call's trace in Grafana/Tempo.
   */
  @Column({ type: 'varchar', length: 32, nullable: true })
  traceId: string | null

  @Column({ type: 'int', nullable: true })
  durationSeconds: number | null

  @Column({ type: 'timestamp', nullable: true })
  startedAt: Date | null

  @Column({ type: 'timestamp', nullable: true })
  endedAt: Date | null

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
