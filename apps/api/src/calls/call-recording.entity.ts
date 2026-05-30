import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  OneToOne,
  JoinColumn,
} from 'typeorm'
import { CallSession } from './call-session.entity'

@Entity('call_recordings')
export class CallRecording {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid', { unique: true })
  callSessionId: string

  @OneToOne(() => CallSession, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'callSessionId' })
  callSession: CallSession

  @Column()
  storageKey: string

  @Column({ default: 'wav' })
  format: string

  @Column('int')
  durationSeconds: number

  @Column({ type: 'bigint', nullable: true })
  sizeBytes: number | null

  @CreateDateColumn()
  createdAt: Date
}
