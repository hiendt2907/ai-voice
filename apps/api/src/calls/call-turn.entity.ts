import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  ManyToOne,
  JoinColumn,
  Index,
  Unique,
} from 'typeorm'
import { CallSession } from './call-session.entity'

export type TurnRole = 'agent' | 'caller' | 'system'

@Entity('call_turns')
@Unique(['callSessionId', 'seq'])
@Index(['callSessionId', 'seq'])
export class CallTurn {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid')
  callSessionId: string

  @ManyToOne(() => CallSession, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'callSessionId' })
  callSession: CallSession

  @Column('int')
  seq: number

  @Column({ type: 'enum', enum: ['agent', 'caller', 'system'] })
  role: TurnRole

  @Column({ type: 'varchar', nullable: true })
  stepId: string | null

  @Column({ type: 'varchar', nullable: true })
  intent: string | null

  @Column({ type: 'text', default: '' })
  text: string

  @Column({ type: 'int', nullable: true })
  audioOffsetMs: number | null

  @Column({ type: 'int', nullable: true })
  latencyMs: number | null

  @Column({ type: 'jsonb', nullable: true })
  metadata: Record<string, unknown> | null

  @CreateDateColumn()
  createdAt: Date
}
