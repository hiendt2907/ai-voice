import { Controller, Post, Get, Patch, Body, Param, Query, Logger } from '@nestjs/common'
import { ApiTags, ApiOperation } from '@nestjs/swagger'
import { IsString, IsOptional, IsArray, IsNumber, IsObject, IsIn } from 'class-validator'
import { CallsService } from '../calls/calls.service'
import { CallbacksService } from '../callbacks/callbacks.service'
import { SettingsService } from '../settings/settings.service'
import { KnowledgeService } from '../knowledge/knowledge.service'
import { LearningService } from '../learning/learning.service'
import { NluService } from '../nlu/nlu.service'
import { ScriptsService } from '../scripts/scripts.service'

class CallEndedDto {
  @IsString()
  sessionId: string

  @IsOptional()
  @IsString()
  campaignId?: string

  @IsOptional()
  @IsString()
  scriptVersionId?: string

  @IsOptional()
  @IsIn(['inbound', 'outbound'])
  direction?: 'inbound' | 'outbound'

  @IsOptional()
  @IsString()
  callerNumber?: string

  @IsIn(['completed', 'handoff', 'error'])
  status: 'completed' | 'handoff' | 'error'

  @IsOptional()
  @IsArray()
  transcript?: Record<string, unknown>[]

  @IsOptional()
  @IsObject()
  slots?: Record<string, string>

  @IsOptional()
  @IsString()
  finalStepId?: string

  @IsOptional()
  @IsNumber()
  durationSeconds?: number

  @IsOptional()
  @IsString()
  startedAt?: string

  @IsOptional()
  @IsString()
  endedAt?: string

  @IsOptional()
  @IsString()
  traceId?: string

  @IsOptional()
  @IsArray()
  turnTraces?: Record<string, unknown>[]

  @IsOptional()
  @IsObject()
  meta?: {
    bargeInCount?: number
    noMatchCounts?: Record<string, number>
    lastRagScore?: number | null
  }
}

class QuestionAnsweredDto {
  @IsString()
  sessionId: string

  @IsString()
  questionId: string

  @IsString()
  answer: string
}

@ApiTags('internal')
@Controller('internal')
export class InternalController {
  private readonly logger = new Logger(InternalController.name)

  constructor(
    private readonly callsService: CallsService,
    private readonly callbacksService: CallbacksService,
    private readonly settingsService: SettingsService,
    private readonly knowledgeService: KnowledgeService,
    private readonly learningService: LearningService,
    private readonly nluService: NluService,
    private readonly scriptsService: ScriptsService,
  ) {}

  @Get('scripts/:campaignId/active')
  @ApiOperation({ summary: 'Get the published script body for a campaign — service-to-service (no auth)' })
  getActiveScript(@Param('campaignId') campaignId: string) {
    return this.scriptsService.getActiveScript(campaignId)
  }

  @Get('knowledge/rag-export')
  @ApiOperation({ summary: 'Export KB articles with embeddings — service-to-service (no auth)' })
  ragExport(@Query('campaignId') campaignId?: string) {
    return this.knowledgeService.listForRag(campaignId)
  }

  @Patch('knowledge/:id/embedding')
  @ApiOperation({ summary: 'Persist article embedding JSON — voice worker service-to-service (no auth)' })
  updateEmbedding(@Param('id') id: string, @Body('embeddingJson') embeddingJson: string) {
    return this.knowledgeService.updateEmbedding(id, embeddingJson)
  }

  @Post('call-events')
  @ApiOperation({ summary: 'Voice worker webhook — call ended event' })
  async handleCallEvent(@Body() dto: CallEndedDto) {
    const session = await this.callsService.handleCallEnded(dto)

    // Phase 7.4: Signal extractor — noMatch turns → auto learning_proposals (pending, not auto-published)
    const noMatchCounts = dto.meta?.noMatchCounts ?? {}
    const noMatchStepIds = Object.entries(noMatchCounts)
      .filter(([, count]) => count > 0)
      .map(([stepId]) => stepId)

    if (noMatchStepIds.length > 0 && dto.campaignId) {
      for (const stepId of noMatchStepIds) {
        try {
          await this.learningService.createProposal({
            type: 'add_reprompt',
            callSessionId: session.id,
            payload: {
              campaignId: dto.campaignId,
              stepId,
              noMatchCount: noMatchCounts[stepId],
              source: 'auto_signal_extractor',
            },
          })
        } catch (err) {
          this.logger.warn(`Failed to create learning proposal for step ${stepId}: ${err}`)
        }
      }
      this.logger.log(
        `Created ${noMatchStepIds.length} learning proposals for session ${session.id}`,
      )
    }

    return { ok: true, id: session.id }
  }

  @Post('question-answered')
  @ApiOperation({ summary: 'Relay answer from Teams/Telegram into active WS session' })
  async questionAnswered(@Body() dto: QuestionAnsweredDto) {
    // Record in DB
    await this.callbacksService.createCallback({
      sessionId: dto.sessionId,
      reason: 'unanswered_question',
      questionText: dto.answer,
    })

    // Phase 3.3: Forward answer to voice worker callbacks endpoint
    const voiceWorkerUrl = process.env.VOICE_WORKER_URL ?? 'http://localhost:8000'
    const callbackUrl = `${voiceWorkerUrl}/callbacks/question/${dto.sessionId}/${dto.questionId}`
    try {
      const resp = await fetch(callbackUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: dto.answer }),
        signal: AbortSignal.timeout(5000),
      })
      if (!resp.ok) {
        this.logger.warn(`Voice worker callback returned ${resp.status} for session ${dto.sessionId}`)
      }
    } catch (err) {
      // Non-fatal: voice worker may be restarting or call already ended
      this.logger.warn(`Failed to forward answer to voice worker: ${err}`)
    }

    return { ok: true, sessionId: dto.sessionId, questionId: dto.questionId }
  }

  @Get('nlu/export')
  @ApiOperation({ summary: 'Export all active NLU documents with embeddings — service-to-service (no auth)' })
  nluExport(@Query('campaignId') campaignId?: string) {
    return this.nluService.listForExport(campaignId)
  }

  @Patch('nlu/:id/embedding')
  @ApiOperation({ summary: 'Persist NLU doc embedding JSON — voice worker service-to-service (no auth)' })
  updateNluEmbedding(@Param('id') id: string, @Body('embeddingJson') embeddingJson: string) {
    return this.nluService.updateEmbedding(id, embeddingJson)
  }

  @Get('system-settings')
  @ApiOperation({ summary: 'All system settings — voice worker calls this on startup' })
  getSystemSettings() {
    return this.settingsService.getAllSettings()
  }
}
