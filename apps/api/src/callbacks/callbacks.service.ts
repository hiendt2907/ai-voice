import { Injectable, Logger, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository, LessThan } from 'typeorm'
import { CallbackRequest } from './callback-request.entity'

class CreateCallbackDto {
  sessionId: string
  callerNumberMasked?: string
  reason: 'unanswered_question' | 'handoff_requested'
  questionText?: string
}

@Injectable()
export class CallbacksService {
  private readonly logger = new Logger(CallbacksService.name)

  constructor(
    @InjectRepository(CallbackRequest)
    private readonly repo: Repository<CallbackRequest>,
  ) {}

  async createCallback(dto: CreateCallbackDto): Promise<CallbackRequest> {
    const cb = this.repo.create({
      sessionId: dto.sessionId,
      callerNumberMasked: dto.callerNumberMasked ?? null,
      reason: dto.reason,
      questionText: dto.questionText ?? null,
      status: 'pending',
      scheduledAt: null,
      completedAt: null,
    })
    return this.repo.save(cb)
  }

  async listPending(): Promise<CallbackRequest[]> {
    return this.repo.find({
      where: { status: 'pending' },
      order: { createdAt: 'ASC' },
    })
  }

  async listAll(): Promise<CallbackRequest[]> {
    return this.repo.find({ order: { createdAt: 'DESC' } })
  }

  async markCompleted(id: string): Promise<CallbackRequest> {
    const cb = await this.repo.findOne({ where: { id } })
    if (!cb) throw new NotFoundException(`CallbackRequest ${id} not found`)
    const updated = { ...cb, status: 'completed' as const, completedAt: new Date() }
    return this.repo.save(updated)
  }

  async checkStaleCallbacks(): Promise<void> {
    const cutoff = new Date(Date.now() - 15 * 60 * 1000) // 15 minutes ago
    const stale = await this.repo.find({
      where: { status: 'pending', createdAt: LessThan(cutoff) },
    })
    if (stale.length > 0) {
      this.logger.warn(`${stale.length} callback request(s) pending > 15 min — escalate`)
    }
  }
}
