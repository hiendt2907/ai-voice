import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  Index,
} from 'typeorm'

export type ProposalStatus = 'pending' | 'approved' | 'rejected'
export type ProposalType = 'new_intent_example' | 'edit_variant' | 'add_reprompt' | 'slot_correction'

@Entity('learning_proposals')
@Index(['status', 'createdAt'])
export class LearningProposal {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid', { nullable: true })
  callSessionId: string | null

  @Column({ type: 'enum', enum: ['new_intent_example', 'edit_variant', 'add_reprompt', 'slot_correction'] })
  type: ProposalType

  @Column({ type: 'jsonb' })
  payload: Record<string, unknown>

  @Column({ type: 'enum', enum: ['pending', 'approved', 'rejected'], default: 'pending' })
  status: ProposalStatus

  @Column({ type: 'varchar', nullable: true })
  reviewedBy: string | null

  @Column({ type: 'text', nullable: true })
  reviewNote: string | null

  @Column({ type: 'timestamp', nullable: true })
  reviewedAt: Date | null

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
