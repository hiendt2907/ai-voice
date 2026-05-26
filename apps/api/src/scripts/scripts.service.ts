import {
  Injectable,
  NotFoundException,
  ConflictException,
  BadRequestException,
} from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { Campaign } from './campaign.entity'
import { ScriptVersion } from './script-version.entity'
import { ScriptLintService } from './lint/script-lint.service'
import { CreateCampaignDto } from './dto/create-campaign.dto'
import { CreateVersionDto } from './dto/create-version.dto'

@Injectable()
export class ScriptsService {
  constructor(
    @InjectRepository(Campaign)
    private readonly campaignRepo: Repository<Campaign>,
    @InjectRepository(ScriptVersion)
    private readonly versionRepo: Repository<ScriptVersion>,
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
      .where('"campaignId" = :campaignId AND status = :status', {
        campaignId,
        status: 'published',
      })
      .execute()
    await this.campaignRepo.update(campaignId, { isActive: true })
    return this.versionRepo.save({
      ...sv,
      status: 'published' as const,
      publishedAt: new Date(),
    })
  }

  private async findVersion(campaignId: string, version: string): Promise<ScriptVersion> {
    await this.getCampaign(campaignId)
    const sv = await this.versionRepo.findOne({ where: { campaignId, version } })
    if (!sv) throw new NotFoundException(`Version ${version} not found for campaign ${campaignId}`)
    return sv
  }
}
