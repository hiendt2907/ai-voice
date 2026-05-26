import { Entity, Column, PrimaryColumn, UpdateDateColumn } from 'typeorm'

@Entity('cloudfone_settings')
export class CloudFoneSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: '' })
  odsUrl: string

  @Column({ default: '' })
  apiKey: string

  @Column({ default: '' })
  tenantId: string

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
