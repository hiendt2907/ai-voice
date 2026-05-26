import { Injectable, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { CallSession } from './call-session.entity'
import { QaScore } from './qa-score.entity'
import { CreateQaScoreDto } from './dto/create-qa-score.dto'

function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length <= 4) return '*'.repeat(digits.length)
  return digits.slice(0, 3) + '*'.repeat(digits.length - 6) + digits.slice(-3)
}

export interface CallEndedPayload {
  sessionId: string
  campaignId?: string
  scriptVersionId?: string
  direction?: 'inbound' | 'outbound'
  callerNumber?: string
  status: 'completed' | 'handoff' | 'error'
  transcript?: Record<string, unknown>[]
  slots?: Record<string, string>
  finalStepId?: string
  durationSeconds?: number
  startedAt?: string
  endedAt?: string
}

@Injectable()
export class CallsService {
  constructor(
    @InjectRepository(CallSession)
    private readonly sessionRepo: Repository<CallSession>,
    @InjectRepository(QaScore)
    private readonly qaRepo: Repository<QaScore>,
  ) {}

  async handleCallEnded(payload: CallEndedPayload): Promise<CallSession> {
    const existing = await this.sessionRepo.findOne({
      where: { sessionId: payload.sessionId },
    })

    const data: Partial<CallSession> = {
      sessionId: payload.sessionId,
      campaignId: payload.campaignId ?? null,
      scriptVersionId: payload.scriptVersionId ?? null,
      direction: payload.direction ?? 'inbound',
      callerNumberMasked: payload.callerNumber ? maskPhone(payload.callerNumber) : null,
      status: payload.status,
      transcript: payload.transcript ?? null,
      slots: payload.slots ?? null,
      finalStepId: payload.finalStepId ?? null,
      durationSeconds: payload.durationSeconds ?? null,
      startedAt: payload.startedAt ? new Date(payload.startedAt) : null,
      endedAt: payload.endedAt ? new Date(payload.endedAt) : new Date(),
    }

    if (existing) {
      return this.sessionRepo.save({ ...existing, ...data })
    }
    return this.sessionRepo.save(this.sessionRepo.create(data))
  }

  async listSessions(
    opts: { page?: number; limit?: number; campaignId?: string } = {},
  ): Promise<{ data: CallSession[]; total: number }> {
    const page = opts.page ?? 1
    const limit = opts.limit ?? 20
    const qb = this.sessionRepo
      .createQueryBuilder('cs')
      .orderBy('cs.createdAt', 'DESC')
      .skip((page - 1) * limit)
      .take(limit)

    if (opts.campaignId) qb.andWhere('cs.campaignId = :cid', { cid: opts.campaignId })

    const [data, total] = await qb.getManyAndCount()
    return { data, total }
  }

  async getSession(id: string): Promise<CallSession> {
    const session = await this.sessionRepo.findOne({ where: { id } })
    if (!session) throw new NotFoundException(`Call session ${id} not found`)
    return session
  }

  async submitQaScore(
    sessionId: string,
    scoredBy: string,
    dto: CreateQaScoreDto,
  ): Promise<QaScore> {
    await this.getSession(sessionId)
    return this.qaRepo.save(
      this.qaRepo.create({
        callSessionId: sessionId,
        scoredBy,
        score: dto.score,
        notes: dto.notes ?? null,
        tags: dto.tags ?? [],
      }),
    )
  }

  async getQaScores(sessionId: string): Promise<QaScore[]> {
    await this.getSession(sessionId)
    return this.qaRepo.find({ where: { callSessionId: sessionId }, order: { createdAt: 'DESC' } })
  }

  async listPendingQa(limit = 20): Promise<CallSession[]> {
    const scored = this.qaRepo
      .createQueryBuilder('qs')
      .select('qs.callSessionId')
      .distinct(true)

    return this.sessionRepo
      .createQueryBuilder('cs')
      .where('cs.status IN (:...statuses)', { statuses: ['completed', 'handoff'] })
      .andWhere(`cs.id NOT IN (${scored.getQuery()})`)
      .orderBy('cs.createdAt', 'DESC')
      .take(limit)
      .getMany()
  }
}
