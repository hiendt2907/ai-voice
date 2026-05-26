import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  Index,
} from 'typeorm'

@Entity('audit_events')
@Index(['actorId', 'createdAt'])
@Index(['entity', 'entityId'])
export class AuditEvent {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column()
  actorId: string

  @Column()
  actorEmail: string

  @Column()
  action: string

  @Column()
  entity: string

  @Column({ type: 'varchar', nullable: true })
  entityId: string | null

  @Column({ type: 'jsonb', nullable: true })
  diff: Record<string, unknown> | null

  @Column({ type: 'varchar', nullable: true })
  ipAddress: string | null

  @CreateDateColumn()
  createdAt: Date
}
