import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('cloudfone_settings')
export class CloudFoneSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: '' })
  socket: string

  @Column({ default: '' })
  port: string

  @Column({ default: '' })
  realm: string

  @Column({ default: '' })
  user: string

  @Column({ default: '' })
  password: string

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
