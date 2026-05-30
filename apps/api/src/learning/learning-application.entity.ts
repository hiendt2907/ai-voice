import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  OneToOne,
  JoinColumn,
} from 'typeorm'
import { LearningProposal } from './learning-proposal.entity'

export type LearningApplicationStatus = 'applied' | 'failed'

@Entity('learning_applications')
export class LearningApplication {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid', { unique: true })
  proposalId: string

  @OneToOne(() => LearningProposal, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'proposalId' })
  proposal: LearningProposal

  @Column('uuid')
  targetCampaignId: string

  @Column({ type: 'uuid', nullable: true })
  resultVersionId: string | null

  @Column('uuid')
  appliedBy: string

  @CreateDateColumn()
  appliedAt: Date

  @Column({
    type: 'enum',
    enum: ['applied', 'failed'],
    default: 'applied',
  })
  status: LearningApplicationStatus
}
