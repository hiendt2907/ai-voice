import { Injectable } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository, Between } from 'typeorm'
import { AuditEvent } from './audit-event.entity'

export interface LogAuditParams {
  actorId: string
  actorEmail: string
  action: string
  entity: string
  entityId?: string
  diff?: Record<string, unknown>
  ipAddress?: string
}

@Injectable()
export class AuditService {
  constructor(@InjectRepository(AuditEvent) private readonly repo: Repository<AuditEvent>) {}

  async log(params: LogAuditParams): Promise<void> {
    const event = this.repo.create(params)
    await this.repo.save(event)
  }

  async findAll(opts: {
    actorId?: string
    entity?: string
    action?: string
    from?: Date
    to?: Date
    limit?: number
    offset?: number
  }): Promise<[AuditEvent[], number]> {
    const qb = this.repo.createQueryBuilder('e').orderBy('e.createdAt', 'DESC')

    if (opts.actorId) qb.andWhere('e.actorId = :actorId', { actorId: opts.actorId })
    if (opts.entity) qb.andWhere('e.entity = :entity', { entity: opts.entity })
    if (opts.action) qb.andWhere('e.action = :action', { action: opts.action })
    if (opts.from && opts.to) qb.andWhere('e.createdAt BETWEEN :from AND :to', { from: opts.from, to: opts.to })

    qb.limit(opts.limit ?? 50).offset(opts.offset ?? 0)

    return qb.getManyAndCount()
  }
}
