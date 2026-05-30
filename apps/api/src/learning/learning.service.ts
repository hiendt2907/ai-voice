import { Injectable, NotFoundException, BadRequestException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { LearningProposal } from './learning-proposal.entity'
import { LearningApplication } from './learning-application.entity'
import { CreateProposalDto } from './dto/create-proposal.dto'
import { ScriptsService } from '../scripts/scripts.service'

@Injectable()
export class LearningService {
  constructor(
    @InjectRepository(LearningProposal)
    private readonly proposalRepo: Repository<LearningProposal>,
    @InjectRepository(LearningApplication)
    private readonly applicationRepo: Repository<LearningApplication>,
    private readonly scriptsService: ScriptsService,
  ) {}

  createProposal(dto: CreateProposalDto) {
    return this.proposalRepo.save(
      this.proposalRepo.create({
        type: dto.type,
        payload: dto.payload,
        callSessionId: dto.callSessionId ?? null,
        status: 'pending',
      }),
    )
  }

  listProposals(status?: string) {
    const qb = this.proposalRepo.createQueryBuilder('lp').orderBy('lp.createdAt', 'DESC')
    if (status) qb.andWhere('lp.status = :status', { status })
    return qb.getMany()
  }

  async reviewProposal(
    id: string,
    decision: 'approved' | 'rejected',
    reviewedBy: string,
    reviewNote?: string,
  ) {
    const proposal = await this.proposalRepo.findOne({ where: { id } })
    if (!proposal) throw new NotFoundException(`Proposal ${id} not found`)
    if (proposal.status !== 'pending') {
      throw new BadRequestException(`Proposal ${id} is already ${proposal.status}`)
    }
    return this.proposalRepo.save({
      ...proposal,
      status: decision,
      reviewedBy,
      reviewNote: reviewNote ?? null,
      reviewedAt: new Date(),
    })
  }

  async applyProposal(id: string, appliedBy: string) {
    const proposal = await this.proposalRepo.findOne({ where: { id } })
    if (!proposal) throw new NotFoundException(`Proposal ${id} not found`)
    if (proposal.status !== 'approved') {
      throw new BadRequestException(`Proposal ${id} must be approved before applying`)
    }

    const campaignId = (proposal.payload as { campaignId?: string }).campaignId
    if (!campaignId) {
      throw new BadRequestException(`Proposal payload missing campaignId`)
    }

    const versions = await this.scriptsService.listVersions(campaignId)
    const published = versions.find((v) => v.status === 'published')
    const baseBody = (published?.body ?? {}) as Record<string, unknown>

    // Phase 7.2: merge proposal.payload into draft body (deep-merge top-level keys)
    const payloadPatch = (proposal.payload as { patch?: Record<string, unknown> }).patch ?? {}
    const mergedBody: Record<string, unknown> = { ...baseBody, ...payloadPatch }

    const newVersion = `${new Date().toISOString().slice(0, 10)}-hitl`
    const newScriptVersion = await this.scriptsService.createVersion(
      campaignId,
      { version: newVersion, body: mergedBody },
      appliedBy,
    )

    // Phase 7.3: record learning_applications row
    const application = await this.applicationRepo.save(
      this.applicationRepo.create({
        proposalId: proposal.id,
        targetCampaignId: campaignId,
        resultVersionId: newScriptVersion.id,
        appliedBy,
        status: 'applied',
      }),
    )

    return { proposal, application, scriptVersion: newScriptVersion }
  }
}
