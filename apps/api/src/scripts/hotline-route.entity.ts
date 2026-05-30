import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
} from 'typeorm'

@Entity('hotline_routes')
export class HotlineRoute {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column({ unique: true })
  hotlineNumber: string

  @Column('uuid')
  campaignId: string

  @Column({ default: true })
  isActive: boolean

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
