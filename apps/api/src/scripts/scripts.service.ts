import {
  Injectable,
  NotFoundException,
  ConflictException,
  BadRequestException,
  ServiceUnavailableException,
} from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository, Not, IsNull } from 'typeorm'
import { Campaign } from './campaign.entity'
import { ScriptVersion } from './script-version.entity'
import { VoiceProfile } from './voice-profile.entity'
import { KnowledgeArticle } from '../knowledge/knowledge-article.entity'
import { NluDocument } from '../nlu/nlu-document.entity'
import { ScriptLintService } from './lint/script-lint.service'
import { CreateCampaignDto } from './dto/create-campaign.dto'
import { CreateVersionDto } from './dto/create-version.dto'
import { PatchCampaignDto } from './dto/patch-campaign.dto'
import { UpsertVoiceProfileDto } from './dto/upsert-voice-profile.dto'
import { VoiceWorkerUrlResolver } from '../common/voice-worker-url.resolver'

@Injectable()
export class ScriptsService {
  constructor(
    @InjectRepository(Campaign)
    private readonly campaignRepo: Repository<Campaign>,
    @InjectRepository(ScriptVersion)
    private readonly versionRepo: Repository<ScriptVersion>,
    @InjectRepository(VoiceProfile)
    private readonly voiceProfileRepo: Repository<VoiceProfile>,
    @InjectRepository(KnowledgeArticle)
    private readonly kbRepo: Repository<KnowledgeArticle>,
    @InjectRepository(NluDocument)
    private readonly nluRepo: Repository<NluDocument>,
    private readonly lintService: ScriptLintService,
    private readonly voiceWorkerUrlResolver: VoiceWorkerUrlResolver,
  ) {}

  validate(body: Record<string, unknown>) {
    return this.lintService.lint(body)
  }

  listCampaigns() {
    return this.campaignRepo.find({ order: { createdAt: 'DESC' } })
  }

  createCampaign(dto: CreateCampaignDto) {
    return this.campaignRepo.save(
      this.campaignRepo.create({
        name: dto.name,
        direction: dto.direction,
        voiceProfile: dto.voiceProfile,
      }),
    )
  }

  async patchCampaign(id: string, dto: PatchCampaignDto): Promise<Campaign> {
    const campaign = await this.campaignRepo.findOne({ where: { id } })
    if (!campaign) throw new NotFoundException(`Campaign ${id} not found`)
    return this.campaignRepo.save({ ...campaign, ...dto })
  }

  async getCampaign(id: string) {
    const campaign = await this.campaignRepo.findOne({
      where: { id },
      relations: ['versions'],
    })
    if (!campaign) throw new NotFoundException(`Campaign ${id} not found`)
    return campaign
  }

  /**
   * `campaign.interceptionMode`/`interceptionDomains` được gắn thêm vào đây vì
   * đây là endpoint DUY NHẤT voice worker gọi lúc bắt đầu cuộc gọi để lấy
   * script — trước đây các trường này tồn tại trong DB, có UI chọn Shadow/
   * Medium/Full (InterceptionModeSelector.tsx) nhưng KHÔNG BAO GIỜ được voice
   * worker đọc: ws.py chỉ nhận interception_mode từ chính message "start" của
   * client, và không nơi nào trong repo (SIP bridge, simulator, CloudFone
   * relay) từng gửi trường đó — mọi cuộc gọi thật luôn chạy mặc định "full"
   * bất kể admin chọn gì trên Portal. Không đổi shape của `version` (chỉ có
   * `.body` được ws.py:_fetch_active_script đọc từ trước) — chỉ thêm field
   * mới, không phá consumer cũ.
   */
  async getActiveScript(campaignId: string): Promise<ScriptVersion & { interceptionMode: string; interceptionDomains: string[] }> {
    const campaign = await this.getCampaign(campaignId)
    const version = await this.versionRepo.findOne({
      where: { campaignId, status: 'published' },
    })
    if (!version) throw new NotFoundException(`No published version for campaign ${campaignId}`)
    return {
      ...version,
      interceptionMode: campaign.interceptionMode,
      interceptionDomains: campaign.interceptionDomains ?? [],
    }
  }

  async listVersions(campaignId: string) {
    await this.getCampaign(campaignId)
    return this.versionRepo.find({
      where: { campaignId },
      order: { createdAt: 'DESC' },
    })
  }

  async createVersion(campaignId: string, dto: CreateVersionDto, createdBy: string) {
    await this.getCampaign(campaignId)
    const existing = await this.versionRepo.findOne({ where: { campaignId, version: dto.version } })
    if (existing) {
      throw new ConflictException(`Version ${dto.version} already exists for campaign ${campaignId}`)
    }
    const lintResult = this.lintService.lint(dto.body)
    if (!lintResult.valid) {
      throw new BadRequestException({ message: 'Script validation failed', errors: lintResult.errors })
    }
    return this.versionRepo.save(
      this.versionRepo.create({ campaignId, version: dto.version, body: dto.body, createdBy }),
    )
  }

  async submitForReview(campaignId: string, version: string) {
    const sv = await this.findVersion(campaignId, version)
    if (sv.status !== 'draft') {
      throw new BadRequestException(`Version ${version} status is '${sv.status}', expected 'draft'`)
    }
    return this.versionRepo.save({ ...sv, status: 'under_review' as const })
  }

  async publishVersion(campaignId: string, version: string) {
    const sv = await this.findVersion(campaignId, version)
    if (sv.status !== 'under_review') {
      throw new BadRequestException(
        `Version ${version} status is '${sv.status}', expected 'under_review'`,
      )
    }
    await this.versionRepo
      .createQueryBuilder()
      .update()
      .set({ status: 'archived' })
      .where('"campaignId" = :campaignId AND status = :status', { campaignId, status: 'published' })
      .execute()
    const published = await this.versionRepo.save({
      ...sv,
      status: 'published' as const,
      publishedAt: new Date(),
    })
    await this.campaignRepo.update(campaignId, { isActive: true, publishedVersionId: published.id })
    return published
  }

  async deleteCampaign(id: string): Promise<void> {
    const campaign = await this.campaignRepo.findOne({ where: { id } })
    if (!campaign) throw new NotFoundException(`Campaign ${id} not found`)
    await this.versionRepo.delete({ campaignId: id })
    await this.campaignRepo.delete(id)
  }

  /**
   * "Related" = what the voice worker will actually use for this campaign
   * at call time — computed live from the exact same rules
   * services/voice/rag/store.py::_tag_matches and nlu/store.py::search_intents
   * apply, not a separately-maintained scriptId assignment. Two parallel
   * mechanisms (a stored FK the Portal checklist counted, vs. the
   * linkedKbTags/campaignId filters runtime actually evaluates) used to
   * drift out of sync — a campaign could show "0 KB articles" in Portal
   * while the AI was still answering from KB via tag matches, or vice
   * versa. One source of truth now: this mirrors runtime exactly.
   */
  async getRelated(campaignId: string) {
    const campaign = await this.getCampaign(campaignId)
    const publishedVersion = campaign.versions?.find((v) => v.id === campaign.publishedVersionId)
    const linkedKbTags: string[] = (publishedVersion?.body as Record<string, unknown>)?.linkedKbTags as string[] ?? []

    const allActiveArticles = await this.kbRepo.find({ where: { isActive: true }, order: { createdAt: 'DESC' } })
    const kbArticles = linkedKbTags.includes('*')
      ? allActiveArticles
      : allActiveArticles.filter((a) => {
          if (linkedKbTags.length === 0) return false
          if (a.category && linkedKbTags.includes(a.category)) return true
          return (a.tags ?? []).some((t) => linkedKbTags.includes(t))
        })

    const nluDocs = await this.nluRepo.find({
      where: [{ campaignId, isActive: true }, { campaignId: IsNull(), isActive: true }],
      order: { createdAt: 'DESC' },
    })

    return { kbArticles, nluDocs, linkedKbTags }
  }

  private async findVersion(campaignId: string, version: string): Promise<ScriptVersion> {
    await this.getCampaign(campaignId)
    const sv = await this.versionRepo.findOne({ where: { campaignId, version } })
    if (!sv) throw new NotFoundException(`Version ${version} not found for campaign ${campaignId}`)
    return sv
  }

  // ── Voice Profiles ────────────────────────────────────────────────────────

  listVoiceProfiles() {
    return this.voiceProfileRepo.find({ where: { isActive: true }, order: { createdAt: 'DESC' } })
  }

  async getVoiceProfile(id: string): Promise<VoiceProfile> {
    const profile = await this.voiceProfileRepo.findOne({ where: { id } })
    if (!profile) throw new NotFoundException(`Voice profile ${id} not found`)
    return profile
  }

  createVoiceProfile(dto: UpsertVoiceProfileDto): Promise<VoiceProfile> {
    return this.voiceProfileRepo.save(
      this.voiceProfileRepo.create({ id: crypto.randomUUID(), ...dto, ttsVoiceId: dto.ttsVoiceId ?? dto.elevenlabsVoiceId ?? '' }),
    )
  }

  async updateVoiceProfile(id: string, dto: UpsertVoiceProfileDto): Promise<VoiceProfile> {
    const existing = await this.getVoiceProfile(id)
    return this.voiceProfileRepo.save({ ...existing, ...dto })
  }

  async deactivateVoiceProfile(id: string): Promise<void> {
    await this.getVoiceProfile(id)
    await this.voiceProfileRepo.update(id, { isActive: false })
  }

  /**
   * Tổng hợp thử một câu mẫu bằng cấu hình giọng của profile, gọi voice
   * worker qua `VoiceWorkerUrlResolver` (dùng chung với nlu.service.ts /
   * knowledge.service.ts — DB `voice_worker_settings.internalUrl` -> env
   * `VOICE_WORKER_URL` -> localhost).
   *
   * Gọi POST /preview/voice — endpoint tổng hợp audio thật. Lưu ý phân biệt
   * với POST /preview (không có hậu tố), vốn chỉ canh nhịp ngắt câu cho kịch
   * bản và không hề chạm tới TTS engine nào.
   *
   * Voice worker trả WAV base64 (PCM 8kHz đã được bọc header RIFF) vì thẻ
   * <audio> của trình duyệt không phát được PCM thô.
   */
  async previewVoiceProfile(id: string): Promise<{ audioBase64: string }> {
    const profile = await this.getVoiceProfile(id)
    const base = await this.voiceWorkerUrlResolver.resolve()
    const text = `Xin chào, đây là giọng đọc thử của ${profile.displayName}.`

    // elevenlabsVoiceId chỉ dùng cho engine elevenlabs; các engine khác đọc
    // tên giọng từ ttsVoiceId. Voice worker tự route theo engine.
    const voice =
      profile.ttsEngine === 'elevenlabs'
        ? (profile.elevenlabsVoiceId ?? profile.ttsVoiceId)
        : profile.ttsVoiceId

    let res: Response
    try {
      res = await fetch(`${base}/preview/voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          engine: profile.ttsEngine,
          voice,
          stability: profile.stabilityFactor,
          similarity_boost: profile.similarityBoost,
          style: profile.styleExaggeration,
          use_speaker_boost: profile.useSpeakerBoost,
        }),
        // Tổng hợp cả câu (không streaming) nên chậm hơn TTFA một lượt thoại;
        // 8s không đủ khi engine phải fallback sang engine thứ hai.
        signal: AbortSignal.timeout(20000),
      })
    } catch {
      throw new ServiceUnavailableException('Không kết nối được tới voice worker để tổng hợp giọng thử')
    }

    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      throw new ServiceUnavailableException(
        `Voice worker trả lỗi khi tổng hợp giọng thử (HTTP ${res.status})${detail ? `: ${detail.slice(0, 300)}` : ''}`,
      )
    }

    const body = (await res.json()) as { audioBase64?: string }
    if (!body.audioBase64) {
      throw new ServiceUnavailableException(
        'Voice worker không trả về dữ liệu âm thanh cho giọng thử',
      )
    }
    return { audioBase64: body.audioBase64 }
  }
}
