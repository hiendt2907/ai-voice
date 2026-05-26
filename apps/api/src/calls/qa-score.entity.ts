import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  ManyToOne,
  JoinColumn,
  Index,
} from 'typeorm'
import { CallSession } from './call-session.entity'

@Entity('qa_scores')
@Index(['callSessionId'])
export class QaScore {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid')
  callSessionId: string

  @ManyToOne(() => CallSession)
  @JoinColumn({ name: 'callSessionId' })
  callSession: CallSession

  @Column('uuid')
  scoredBy: string

  @Column({ type: 'smallint' })
  score: number

  @Column({ type: 'text', nullable: true })
  notes: string | null

  @Column({ type: 'jsonb', default: '[]' })
  tags: string[]

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
