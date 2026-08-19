import { Controller, Get, Put, Post, Body, UseGuards, Request } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { SettingsService } from './settings.service'
import { AuditService } from '../audit/audit.service'
import { UpsertCloudFoneDto } from './dto/upsert-cloudfone.dto'
import { UpsertAiDto } from './dto/upsert-ai.dto'
import { UpsertSttDto } from './dto/upsert-stt.dto'
import { UpsertTtsDto } from './dto/upsert-tts.dto'
import { UpsertNotifyDto } from './dto/upsert-notify.dto'
import { UpsertVoiceWorkerDto } from './dto/upsert-voice-worker.dto'
import { UpsertDoctorCheckDto } from './dto/upsert-doctorcheck.dto'
import { UpsertConversationDto } from './dto/upsert-conversation.dto'

interface AuthRequest {
  user: { userId: string; email: string }
}

@ApiTags('settings')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('settings')
export class SettingsController {
  constructor(
    private readonly svc: SettingsService,
    private readonly audit: AuditService,
  ) {}

  // ── CloudFone ─────────────────────────────────────────────────────────────

  @Get('cloudfone')
  @ApiOperation({ summary: 'Get CloudFone connection settings' })
  getCloudFone() {
    return this.svc.getCloudFone()
  }

  @Put('cloudfone')
  @Roles('admin')
  @ApiOperation({ summary: 'Update CloudFone connection settings (admin only)' })
  async upsertCloudFone(@Body() dto: UpsertCloudFoneDto, @Request() req: AuthRequest) {
    const before = await this.svc.getCloudFone()
    const after = await this.svc.upsertCloudFone(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'cloudfone_settings', entityId: 'default',
      diff: { before: { socket: before.socket, user: before.user }, after: { socket: dto.socket, user: dto.user } },
    })
    return after
  }

  @Post('cloudfone/test')
  @Roles('admin')
  @ApiOperation({ summary: 'Test CloudFone WS connectivity' })
  testCloudFone() {
    return this.svc.testCloudFoneConnection()
  }

  // ── AI / LLM ──────────────────────────────────────────────────────────────

  @Get('ai')
  @ApiOperation({ summary: 'Get AI / LLM settings' })
  getAi() {
    return this.svc.getAi()
  }

  @Put('ai')
  @Roles('admin')
  @ApiOperation({ summary: 'Update AI / LLM settings (admin only)' })
  async upsertAi(@Body() dto: UpsertAiDto, @Request() req: AuthRequest) {
    const before = await this.svc.getAi()
    const after = await this.svc.upsertAi(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'ai_settings', entityId: 'default',
      diff: { before: { ollamaBaseUrl: before.ollamaBaseUrl, ollamaModel: before.ollamaModel }, after: { ollamaBaseUrl: dto.ollamaBaseUrl, ollamaModel: dto.ollamaModel } },
    })
    void this.svc.notifyVoiceWorkerConfigReload()
    return after
  }

  // ── STT ───────────────────────────────────────────────────────────────────

  @Get('stt')
  @ApiOperation({ summary: 'Get STT settings' })
  getStt() {
    return this.svc.getStt()
  }

  @Put('stt')
  @Roles('admin')
  @ApiOperation({ summary: 'Update STT settings (admin only)' })
  async upsertStt(@Body() dto: UpsertSttDto, @Request() req: AuthRequest) {
    const before = await this.svc.getStt()
    const after = await this.svc.upsertStt(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'stt_settings', entityId: 'default',
      diff: { before: { modelSize: before.modelSize, device: before.device }, after: { modelSize: dto.modelSize, device: dto.device } },
    })
    return after
  }

  // ── TTS ───────────────────────────────────────────────────────────────────

  @Get('tts')
  @ApiOperation({ summary: 'Get TTS settings' })
  getTts() {
    return this.svc.getTts()
  }

  @Get('tts/health')
  @ApiOperation({ summary: 'TTS engine health — circuit breaker + quota status' })
  async getTtsHealth() {
    return this.svc.getTtsHealth()
  }

  @Put('tts')
  @Roles('admin')
  @ApiOperation({ summary: 'Update TTS settings (admin only)' })
  async upsertTts(@Body() dto: UpsertTtsDto, @Request() req: AuthRequest) {
    const before = await this.svc.getTts()
    const after = await this.svc.upsertTts(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'tts_settings', entityId: 'default',
      diff: {
        before: { engine: before.engine, voice: before.voice, engineFallbackOrder: before.engineFallbackOrder },
        after: { engine: dto.engine, voice: dto.voice, engineFallbackOrder: dto.engineFallbackOrder },
      },
    })
    void this.svc.notifyVoiceWorkerConfigReload()
    return after
  }

  // ── Notify ────────────────────────────────────────────────────────────────

  @Get('notify')
  @ApiOperation({ summary: 'Get notification settings (token masked)' })
  getNotify() {
    return this.svc.getNotify()
  }

  @Put('notify')
  @Roles('admin')
  @ApiOperation({ summary: 'Update notification settings (admin only)' })
  async upsertNotify(@Body() dto: UpsertNotifyDto, @Request() req: AuthRequest) {
    const before = await this.svc.getNotify()
    const after = await this.svc.upsertNotify(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'notify_settings', entityId: 'default',
      diff: { before: { platform: before.platform, telegramGroupId: before.telegramGroupId }, after: { platform: dto.platform, telegramGroupId: dto.telegramGroupId } },
    })
    return after
  }

  // ── Voice Worker ──────────────────────────────────────────────────────────

  @Get('voice-worker')
  @ApiOperation({ summary: 'Get voice worker settings' })
  getVoiceWorker() {
    return this.svc.getVoiceWorker()
  }

  @Put('voice-worker')
  @Roles('admin')
  @ApiOperation({ summary: 'Update voice worker settings (admin only)' })
  async upsertVoiceWorker(@Body() dto: UpsertVoiceWorkerDto, @Request() req: AuthRequest) {
    const before = await this.svc.getVoiceWorker()
    const after = await this.svc.upsertVoiceWorker(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'voice_worker_settings', entityId: 'default',
      diff: {
        before: { internalUrl: before.internalUrl, maxConcurrentSessions: before.maxConcurrentSessions },
        after: { internalUrl: dto.internalUrl, maxConcurrentSessions: dto.maxConcurrentSessions },
      },
    })
    return after
  }

  // ── DoctorCheck ───────────────────────────────────────────────────────────

  @Get('doctorcheck')
  @ApiOperation({ summary: 'Get DoctorCheck API settings' })
  getDoctorCheck() {
    return this.svc.getDoctorCheck()
  }

  @Put('doctorcheck')
  @Roles('admin')
  @ApiOperation({ summary: 'Update DoctorCheck API settings (admin only)' })
  async upsertDoctorCheck(@Body() dto: UpsertDoctorCheckDto, @Request() req: AuthRequest) {
    const before = await this.svc.getDoctorCheck()
    const after = await this.svc.upsertDoctorCheck(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'doctorcheck_settings', entityId: 'default',
      diff: { before: { baseUrl: before.baseUrl }, after: { baseUrl: dto.baseUrl } },
    })
    return after
  }

  @Post('doctorcheck/test')
  @Roles('admin')
  @ApiOperation({ summary: 'Test DoctorCheck API connectivity' })
  testDoctorCheck() {
    return this.svc.testDoctorCheckConnection()
  }

  // ── Conversation ──────────────────────────────────────────────────────────

  @Get('conversation')
  @ApiOperation({ summary: 'Get LLM Conversation settings' })
  getConversation() {
    return this.svc.getConversation()
  }

  @Put('conversation')
  @Roles('admin')
  @ApiOperation({ summary: 'Update LLM Conversation settings (admin only)' })
  async upsertConversation(@Body() dto: UpsertConversationDto, @Request() req: AuthRequest) {
    const before = await this.svc.getConversation()
    const after = await this.svc.upsertConversation(dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId, actorEmail: req.user.email, action: 'update',
      entity: 'conversation_settings', entityId: 'default',
      diff: {
        before: { enabled: before.enabled, ollamaModel: before.ollamaModel, sentimentEnabled: before.sentimentEnabled },
        after: { enabled: dto.enabled, ollamaModel: dto.ollamaModel, sentimentEnabled: dto.sentimentEnabled },
      },
    })
    return after
  }
}
