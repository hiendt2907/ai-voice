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
import { Campaign } from './campaign.entity'

export type ScriptVersionStatus = 'draft' | 'under_review' | 'published' | 'archived'

@Entity('script_versions')
@Index(['campaignId', 'status'])
export class ScriptVersion {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid')
  campaignId: string

  @ManyToOne(() => Campaign, (c) => c.versions)
  @JoinColumn({ name: 'campaignId' })
  campaign: Campaign

  @Column()
  version: string

  @Column({ type: 'jsonb' })
  body: Record<string, unknown>

  @Column({
    type: 'enum',
    enum: ['draft', 'under_review', 'published', 'archived'],
    default: 'draft',
  })
  status: ScriptVersionStatus

  @Column({ type: 'text', nullable: true })
  reviewNote: string | null

  @Column({ type: 'varchar', nullable: true })
  createdBy: string | null

  @Column({ type: 'timestamp', nullable: true })
  publishedAt: Date | null

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
