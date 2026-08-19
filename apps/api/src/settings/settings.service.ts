import { Injectable, OnModuleDestroy } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import Redis from 'ioredis'
import { CloudFoneSettings } from './cloudfone-settings.entity'
import { AiSettings } from './ai-settings.entity'
import { SttSettings } from './stt-settings.entity'
import { TtsSettings } from './tts-settings.entity'
import { NotifySettings } from './notify-settings.entity'
import { VoiceWorkerSettings } from './voice-worker-settings.entity'
import { DoctorCheckSettings } from './doctorcheck-settings.entity'
import { ConversationSettings } from './conversation-settings.entity'
import { UpsertCloudFoneDto } from './dto/upsert-cloudfone.dto'
import { UpsertAiDto } from './dto/upsert-ai.dto'
import { UpsertSttDto } from './dto/upsert-stt.dto'
import { UpsertTtsDto } from './dto/upsert-tts.dto'
import { UpsertNotifyDto } from './dto/upsert-notify.dto'
import { UpsertVoiceWorkerDto } from './dto/upsert-voice-worker.dto'
import { UpsertDoctorCheckDto } from './dto/upsert-doctorcheck.dto'
import { UpsertConversationDto } from './dto/upsert-conversation.dto'

const DEFAULT_ID = 'default'
const VOICE_CONFIG_CACHE_KEY = 'config:system'

let _redis: Redis | null = null
function getRedis(): Redis {
  if (!_redis) {
    _redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379', { lazyConnect: true, enableOfflineQueue: false })
  }
  return _redis
}

async function invalidateVoiceConfigCache(): Promise<void> {
  try {
    await getRedis().del(VOICE_CONFIG_CACHE_KEY)
  } catch {
    // non-fatal — voice worker will reload on next TTL expiry
  }
}

export interface SystemSettings {
  cloudfone: CloudFoneSettings
  ai: AiSettings
  stt: SttSettings
  tts: TtsSettings
  notify: Omit<NotifySettings, 'telegramBotToken'> & { telegramBotToken: string }
  voiceWorker: VoiceWorkerSettings
  conversation: ConversationSettings
}

@Injectable()
export class SettingsService implements OnModuleDestroy {
  constructor(
    @InjectRepository(CloudFoneSettings)
    private readonly cloudfoneRepo: Repository<CloudFoneSettings>,
    @InjectRepository(AiSettings)
    private readonly aiRepo: Repository<AiSettings>,
    @InjectRepository(SttSettings)
    private readonly sttRepo: Repository<SttSettings>,
    @InjectRepository(TtsSettings)
    private readonly ttsRepo: Repository<TtsSettings>,
    @InjectRepository(NotifySettings)
    private readonly notifyRepo: Repository<NotifySettings>,
    @InjectRepository(VoiceWorkerSettings)
    private readonly voiceWorkerRepo: Repository<VoiceWorkerSettings>,
    @InjectRepository(DoctorCheckSettings)
    private readonly doctorCheckRepo: Repository<DoctorCheckSettings>,
    @InjectRepository(ConversationSettings)
    private readonly conversationRepo: Repository<ConversationSettings>,
  ) {}

  async getCloudFone(): Promise<CloudFoneSettings> {
    const row = await this.cloudfoneRepo.findOne({ where: { id: DEFAULT_ID } })
    if (!row) return this.cloudfoneRepo.create({ id: DEFAULT_ID, socket: '', port: '', realm: '', user: '', password: '' })
    return row
  }

  async upsertCloudFone(dto: UpsertCloudFoneDto, updatedBy: string): Promise<CloudFoneSettings> {
    return this.cloudfoneRepo.save({ id: DEFAULT_ID, ...dto, updatedBy })
  }

  async testCloudFoneConnection(): Promise<{ ok: boolean; message: string }> {
    const settings = await this.getCloudFone()
    if (!settings.socket || !settings.user) {
      return { ok: false, message: 'Chưa cấu hình Socket hoặc User' }
    }
    // Extract hostname from socket URL (strip scheme)
    const hostname = settings.socket.replace(/^wss?:\/\//, '')
    const port = settings.port ? parseInt(settings.port, 10) : 443
    const label = `${hostname}:${port}`

    return new Promise((resolve) => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const tls = require('tls') as typeof import('tls')
      const socket = tls.connect({ host: hostname, port, rejectUnauthorized: true }, () => {
        socket.destroy()
        resolve({ ok: true, message: `Kết nối TLS thành công tới ${label}` })
      })
      socket.setTimeout(5000)
      socket.on('timeout', () => {
        socket.destroy()
        resolve({ ok: false, message: `Timeout kết nối tới ${label}` })
      })
      socket.on('error', (err: Error) => {
        resolve({ ok: false, message: `Lỗi kết nối ${label}: ${err.message}` })
      })
    })
  }

  async getAi(): Promise<AiSettings> {
    const row = await this.aiRepo.findOne({ where: { id: DEFAULT_ID } })
    return row ?? this.aiRepo.create({ id: DEFAULT_ID })
  }

  async upsertAi(dto: UpsertAiDto, updatedBy: string): Promise<AiSettings> {
    return this.aiRepo.save({ id: DEFAULT_ID, ...dto, updatedBy })
  }

  async getStt(): Promise<SttSettings> {
    const row = await this.sttRepo.findOne({ where: { id: DEFAULT_ID } })
    return row ?? this.sttRepo.create({ id: DEFAULT_ID })
  }

  async upsertStt(dto: UpsertSttDto, updatedBy: string): Promise<SttSettings> {
    return this.sttRepo.save({ id: DEFAULT_ID, ...dto, updatedBy })
  }

  async getTts(): Promise<TtsSettings & { elevenlabsApiKey: string }> {
    const row = await this.ttsRepo.findOne({ where: { id: DEFAULT_ID } })
    const base = row ?? this.ttsRepo.create({ id: DEFAULT_ID })
    return { ...base, elevenlabsApiKey: base.elevenlabsApiKey ? '***' : '' }
  }

  private async getTtsRaw(): Promise<TtsSettings> {
    const row = await this.ttsRepo.findOne({ where: { id: DEFAULT_ID } })
    return row ?? this.ttsRepo.create({ id: DEFAULT_ID })
  }

  async upsertTts(dto: UpsertTtsDto, updatedBy: string): Promise<TtsSettings & { elevenlabsApiKey: string }> {
    const existing = await this.ttsRepo.findOne({ where: { id: DEFAULT_ID } })
    const apiKey = dto.elevenlabsApiKey === '***'
      ? (existing?.elevenlabsApiKey ?? null)
      : (dto.elevenlabsApiKey ?? null)
    const saved = await this.ttsRepo.save({
      id: DEFAULT_ID, ...dto, elevenlabsApiKey: apiKey, updatedBy,
    })
    void invalidateVoiceConfigCache()
    return { ...saved, elevenlabsApiKey: saved.elevenlabsApiKey ? '***' : '' }
  }

  async getNotify(): Promise<NotifySettings & { telegramBotToken: string }> {
    const row = await this.notifyRepo.findOne({ where: { id: DEFAULT_ID } })
    const base = row ?? this.notifyRepo.create({ id: DEFAULT_ID })
    return { ...base, telegramBotToken: base.telegramBotToken ? '***' : '' }
  }

  async upsertNotify(dto: UpsertNotifyDto, updatedBy: string): Promise<NotifySettings & { telegramBotToken: string }> {
    const existing = await this.notifyRepo.findOne({ where: { id: DEFAULT_ID } })
    const token = dto.telegramBotToken === '***' ? (existing?.telegramBotToken ?? '') : dto.telegramBotToken
    const saved = await this.notifyRepo.save({ id: DEFAULT_ID, ...dto, telegramBotToken: token, updatedBy })
    return { ...saved, telegramBotToken: saved.telegramBotToken ? '***' : '' }
  }

  async getVoiceWorker(): Promise<VoiceWorkerSettings> {
    const row = await this.voiceWorkerRepo.findOne({ where: { id: DEFAULT_ID } })
    return row ?? this.voiceWorkerRepo.create({ id: DEFAULT_ID })
  }

  async upsertVoiceWorker(dto: UpsertVoiceWorkerDto, updatedBy: string): Promise<VoiceWorkerSettings> {
    return this.voiceWorkerRepo.save({ id: DEFAULT_ID, ...dto, updatedBy })
  }

  async getDoctorCheck(): Promise<DoctorCheckSettings & { apiKey: string }> {
    const row = await this.doctorCheckRepo.findOne({ where: { id: DEFAULT_ID } })
    const base = row ?? this.doctorCheckRepo.create({ id: DEFAULT_ID })
    return { ...base, apiKey: base.apiKey ? '***' : '' }
  }

  async upsertDoctorCheck(dto: UpsertDoctorCheckDto, updatedBy: string): Promise<DoctorCheckSettings & { apiKey: string }> {
    const existing = await this.doctorCheckRepo.findOne({ where: { id: DEFAULT_ID } })
    const apiKey = dto.apiKey === '***' ? (existing?.apiKey ?? null) : (dto.apiKey ?? null)
    const saved = await this.doctorCheckRepo.save({ id: DEFAULT_ID, ...dto, apiKey, updatedBy })
    return { ...saved, apiKey: saved.apiKey ? '***' : '' }
  }

  async testDoctorCheckConnection(): Promise<{ ok: boolean; message: string }> {
    const settings = await this.doctorCheckRepo.findOne({ where: { id: DEFAULT_ID } })
    if (!settings?.baseUrl) {
      return { ok: false, message: 'Base URL chưa được cấu hình' }
    }
    try {
      const res = await fetch(`${settings.baseUrl}/health`, {
        signal: AbortSignal.timeout(5000),
        headers: settings.apiKey ? { Authorization: `Bearer ${settings.apiKey}` } : {},
      })
      if (res.ok) return { ok: true, message: `Kết nối thành công (HTTP ${res.status})` }
      return { ok: false, message: `HTTP ${res.status}` }
    } catch (err) {
      return { ok: false, message: err instanceof Error ? err.message : 'Không thể kết nối' }
    }
  }

  async notifyVoiceWorkerConfigReload(): Promise<void> {
    try {
      const vw = await this.getVoiceWorker()
      const url = `${vw.internalUrl ?? 'http://localhost:8000'}/config/reload`
      await fetch(url, { method: 'POST', signal: AbortSignal.timeout(3000) })
    } catch {
      // non-fatal — voice worker sẽ dùng cache TTL hoặc restart thủ công
    }
  }

  onModuleDestroy() {
    _redis?.disconnect()
  }

  async getTtsHealth(): Promise<object> {
    const vw = await this.getVoiceWorker()
    const base = vw.internalUrl ?? 'http://localhost:8000'
    try {
      const res = await fetch(`${base}/ws/tts-health`, { signal: AbortSignal.timeout(3000) })
      if (res.ok) return res.json() as Promise<object>
      return { error: `voice worker returned ${res.status}` }
    } catch {
      return { error: 'voice worker unreachable' }
    }
  }

  async getConversation(): Promise<ConversationSettings> {
    const row = await this.conversationRepo.findOne({ where: { id: DEFAULT_ID } })
    return row ?? this.conversationRepo.create({ id: DEFAULT_ID })
  }

  async upsertConversation(dto: UpsertConversationDto, updatedBy: string): Promise<ConversationSettings> {
    const saved = await this.conversationRepo.save({ id: DEFAULT_ID, ...dto, updatedBy })
    void invalidateVoiceConfigCache()
    return saved
  }

  async getAllSettings(): Promise<SystemSettings> {
    const [cloudfone, ai, stt, tts, notify, voiceWorker, conversation] = await Promise.all([
      this.getCloudFone(),
      this.getAi(),
      this.getStt(),
      this.getTtsRaw(),
      this.getNotify(),
      this.getVoiceWorker(),
      this.getConversation(),
    ])
    return { cloudfone, ai, stt, tts, notify, voiceWorker, conversation }
  }
}
