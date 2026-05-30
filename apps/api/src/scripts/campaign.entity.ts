import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  OneToMany,
} from 'typeorm'
import type { ScriptVersion } from './script-version.entity'

@Entity('campaigns')
export class Campaign {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column()
  name: string

  @Column({ type: 'enum', enum: ['inbound', 'outbound'] })
  direction: 'inbound' | 'outbound'

  @Column()
  voiceProfile: string

  @Column({ default: false })
  isActive: boolean

  @Column({ type: 'uuid', nullable: true })
  publishedVersionId: string | null

  @Column({ type: 'enum', enum: ['shadow', 'medium', 'full'], default: 'shadow' })
  interceptionMode: 'shadow' | 'medium' | 'full'

  @Column({ type: 'simple-array', default: '' })
  interceptionDomains: string[]

  @OneToMany('ScriptVersion', 'campaign')
  versions: ScriptVersion[]

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
