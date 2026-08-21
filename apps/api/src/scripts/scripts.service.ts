import {
  Injectable,
  NotFoundException,
  ConflictException,
  BadRequestException,
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

  async getActiveScript(campaignId: string): Promise<ScriptVersion> {
    await this.getCampaign(campaignId)
    const version = await this.versionRepo.findOne({
      where: { campaignId, status: 'published' },
    })
    if (!version) throw new NotFoundException(`No published version for campaign ${campaignId}`)
    return version
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
}
