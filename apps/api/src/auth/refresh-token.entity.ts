import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
} from 'typeorm'

@Entity('refresh_tokens')
export class RefreshToken {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column('uuid')
  userId: string

  @Column({ unique: true })
  jti: string

  @Column({ type: 'timestamp with time zone' })
  expiresAt: Date

  @Column({ type: 'timestamp with time zone', nullable: true })
  revokedAt: Date | null

  @CreateDateColumn()
  createdAt: Date
}
