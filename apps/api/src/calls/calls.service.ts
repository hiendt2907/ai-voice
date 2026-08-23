import { Injectable, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import type { QueryDeepPartialEntity } from 'typeorm/query-builder/QueryPartialEntity'
import { Repository } from 'typeorm'
import * as http from 'node:http'
import * as https from 'node:https'
import { CallSession, type CallStatus } from './call-session.entity'
import { QaScore } from './qa-score.entity'
import { CallTurn } from './call-turn.entity'
import { CallRecording } from './call-recording.entity'
import { CallMetrics } from './call-metrics.entity'
import { CreateQaScoreDto } from './dto/create-qa-score.dto'
import { maskPhone } from '../common/pii.util'

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
  /** W3C trace id shared across every hop of the call. */
  traceId?: string
  /** One glassbox decision record per caller turn, in order. */
  turnTraces?: Record<string, unknown>[]
  durationSeconds?: number
  startedAt?: string
  endedAt?: string
  meta?: {
    bargeInCount?: number
    noMatchCounts?: Record<string, number>
    lastRagScore?: number | null
  }
}

@Injectable()
export class CallsService {
  constructor(
    @InjectRepository(CallSession)
    private readonly sessionRepo: Repository<CallSession>,
    @InjectRepository(QaScore)
    private readonly qaRepo: Repository<QaScore>,
    @InjectRepository(CallTurn)
    private readonly turnRepo: Repository<CallTurn>,
    @InjectRepository(CallRecording)
    private readonly recordingRepo: Repository<CallRecording>,
    @InjectRepository(CallMetrics)
    private readonly metricsRepo: Repository<CallMetrics>,
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
      traceId: payload.traceId ?? null,
      durationSeconds: payload.durationSeconds ?? null,
      startedAt: payload.startedAt ? new Date(payload.startedAt) : null,
      endedAt: payload.endedAt ? new Date(payload.endedAt) : new Date(),
    }

    const session = existing
      ? await this.sessionRepo.save({ ...existing, ...data })
      : await this.sessionRepo.save(this.sessionRepo.create(data))

    // Phase 4.2: Dual-write call_turns from transcript
    if (payload.transcript?.length) {
      // Glassbox: the worker sends one decision trace per caller turn. The
      // transcript interleaves caller and agent entries, so walk a separate
      // index over caller turns to line each trace up with the utterance that
      // produced it — see services/voice/obs/turn_trace.py.
      const traces = payload.turnTraces ?? []
      let callerSeen = 0
      const turns = payload.transcript.map((entry, idx) => {
        const role = entry['role'] === 'user' ? 'caller' : 'agent'
        const trace = role === 'caller' ? (traces[callerSeen++] ?? null) : null
        return {
          callSessionId: session.id,
          seq: idx,
          role: role as 'agent' | 'caller',
          stepId: (entry['step_id'] as string) ?? null,
          intent: (entry['intent'] as string) ?? null,
          text: (entry['text'] as string) ?? '',
          metadata: trace,
        }
      })
      // Upsert turns (may be called multiple times for same session)
      await this.turnRepo
        .createQueryBuilder()
        .insert()
        .into(CallTurn)
        // TypeORM's deep-partial mapping can't express a jsonb column typed
        // as an index signature, so the trace object has to be cast here.
        .values(turns as QueryDeepPartialEntity<CallTurn>[])
        .orIgnore()
        .execute()
    }

    // Phase 4.2: Write call_metrics (bargeIn, noMatch, ragScore)
    if (payload.meta) {
      const noMatchCounts = payload.meta.noMatchCounts ?? {}
      const totalNoMatch = Object.values(noMatchCounts).reduce((a, b) => a + b, 0)
      const existing = await this.metricsRepo.findOne({
        where: { callSessionId: session.id },
      })
      const metricsData = {
        callSessionId: session.id,
        bargeInCount: payload.meta.bargeInCount ?? 0,
        noMatchCount: totalNoMatch,
        stepCount: payload.transcript?.length ?? null,
      }
      if (existing) {
        await this.metricsRepo.save({ ...existing, ...metricsData })
      } else {
        await this.metricsRepo.save(this.metricsRepo.create(metricsData))
      }
    }

    return session
  }

  async listSessions(
    opts: { page?: number; limit?: number; campaignId?: string; status?: CallStatus } = {},
  ): Promise<{ data: CallSession[]; total: number }> {
    const page = opts.page ?? 1
    const limit = opts.limit ?? 20
    const qb = this.sessionRepo
      .createQueryBuilder('cs')
      .orderBy('cs.createdAt', 'DESC')
      .skip((page - 1) * limit)
      .take(limit)

    if (opts.campaignId) qb.andWhere('cs.campaignId = :cid', { cid: opts.campaignId })
    // Lọc theo status khi được truyền vào — getManyAndCount() tính `total` dựa trên
    // toàn bộ WHERE (bỏ qua skip/take), nên tổng số bản ghi cũng tự động đúng theo filter.
    if (opts.status) qb.andWhere('cs.status = :status', { status: opts.status })

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

  async getTurns(sessionId: string): Promise<CallTurn[]> {
    await this.getSession(sessionId)
    return this.turnRepo.find({
      where: { callSessionId: sessionId },
      order: { seq: 'ASC' },
    })
  }

  async getRecording(sessionId: string): Promise<CallRecording | null> {
    await this.getSession(sessionId)
    return this.recordingRepo.findOne({ where: { callSessionId: sessionId } })
  }

  async streamRecording(sessionId: string): Promise<{ body: NodeJS.ReadableStream; contentType: string; contentLength?: string } | null> {
    const recording = await this.getRecording(sessionId)
    if (!recording) return null

    const minioUrl = process.env.MINIO_INTERNAL_URL
    if (!minioUrl) return null

    const fileUrl = `${minioUrl}/${recording.storageKey}`
    const mod = fileUrl.startsWith('https') ? https : http
    return new Promise((resolve, reject) => {
      mod.get(fileUrl, (res) => {
        const contentType = res.headers['content-type'] ?? 'audio/wav'
        const contentLength = res.headers['content-length']
        resolve({ body: res, contentType, contentLength })
      }).on('error', reject)
    })
  }

  async getActiveCalls(): Promise<{ sessionId: string; callerNumberMasked: string | null; campaignId: string | null; finalStepId: string | null; durationSeconds: number; startedAt: string | null }[]> {
    const sessions = await this.sessionRepo.find({
      where: { status: 'active' as const },
      order: { createdAt: 'DESC' },
      take: 50,
    })
    return sessions.map((s) => ({
      sessionId: s.sessionId,
      callerNumberMasked: s.callerNumberMasked ?? null,
      campaignId: s.campaignId ?? null,
      finalStepId: s.finalStepId ?? null,
      durationSeconds: s.startedAt
        ? Math.round((Date.now() - new Date(s.startedAt).getTime()) / 1000)
        : 0,
      startedAt: s.startedAt ? s.startedAt.toISOString() : null,
    }))
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
