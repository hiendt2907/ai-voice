import { Injectable, Logger } from '@nestjs/common'
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
  private readonly logger = new Logger(AuditService.name)

  constructor(@InjectRepository(AuditEvent) private readonly repo: Repository<AuditEvent>) {}

  /**
   * Ghi một audit event. Toàn bộ ~17 call site trong repo gọi hàm này theo
   * kiểu "fire-and-forget" (`void this.audit.log(...)`), tức là không ai
   * await hay bắt lỗi từ promise này — nếu insert lỗi (constraint, DB gián
   * đoạn...) mà không được catch ở đây thì đó là unhandled rejection âm
   * thầm: mutation chính (publish script, đổi settings, quay số...) VẪN
   * thành công nhưng KHÔNG có audit trail, vi phạm bất biến "Audit mọi
   * mutation" (CLAUDE.md).
   *
   * Xử lý lỗi tập trung tại đây (thay vì sửa từng call site) để mọi lần gọi
   * `audit.log()` trong tương lai tự động được bảo vệ, giảm chỗ có thể sai
   * sót. Log ở mức `error` kèm đủ ngữ cảnh (actor, action, entity, entityId)
   * để có thể truy lại mutation nào đã mất audit trail và xử lý thủ công/
   * đối chiếu nếu cần.
   *
   * Cố ý KHÔNG re-throw (fail-open): audit ghi lỗi không được phép làm sập
   * mutation nghiệp vụ chính. Đây là lựa chọn vận hành có thể tranh luận —
   * xem khuyến nghị fail-closed trong báo cáo đi kèm thay đổi này.
   */
  async log(params: LogAuditParams): Promise<void> {
    try {
      const event = this.repo.create(params)
      await this.repo.save(event)
    } catch (error) {
      this.logger.error(
        `Ghi audit event THẤT BẠI — mutation đã xảy ra nhưng KHÔNG có audit trail. ` +
          `actor=${params.actorEmail} (${params.actorId}) action=${params.action} ` +
          `entity=${params.entity} entityId=${params.entityId ?? 'n/a'}`,
        error instanceof Error ? error.stack : String(error),
      )
    }
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
