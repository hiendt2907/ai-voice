import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
} from 'typeorm'

@Entity('callback_requests')
export class CallbackRequest {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column({ name: 'session_id' })
  sessionId: string

  @Column({ name: 'caller_number_masked', type: 'varchar', nullable: true })
  callerNumberMasked: string | null

  @Column({
    type: 'enum',
    enum: ['unanswered_question', 'handoff_requested'],
    default: 'unanswered_question',
  })
  reason: 'unanswered_question' | 'handoff_requested'

  @Column({ name: 'question_text', nullable: true, type: 'text' })
  questionText: string | null

  @Column({
    type: 'enum',
    enum: ['pending', 'scheduled', 'completed', 'failed'],
    default: 'pending',
  })
  status: 'pending' | 'scheduled' | 'completed' | 'failed'

  @Column({ name: 'scheduled_at', type: 'timestamp', nullable: true })
  scheduledAt: Date | null

  @Column({ name: 'completed_at', type: 'timestamp', nullable: true })
  completedAt: Date | null

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date
}
