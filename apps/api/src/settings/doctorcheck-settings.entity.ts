import { Entity, PrimaryColumn, Column, UpdateDateColumn } from 'typeorm'

@Entity('doctorcheck_settings')
export class DoctorCheckSettings {
  @PrimaryColumn({ default: 'default' })
  id: string

  @Column({ default: '' })
  baseUrl: string

  @Column({ type: 'varchar', nullable: true, default: null })
  apiKey: string | null

  @Column({ type: 'jsonb', default: {} })
  specialtyMapping: Record<string, string>

  @Column({ type: 'jsonb', default: {} })
  slotMapping: Record<string, string>

  @Column({ default: 'Mã đặt lịch của anh/chị là {{booking_id}} ạ.' })
  bookingConfirmTemplate: string

  @Column({ default: 2 })
  retryCount: number

  @Column({ default: 3000 })
  timeoutMs: number

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @UpdateDateColumn()
  updatedAt: Date
}
