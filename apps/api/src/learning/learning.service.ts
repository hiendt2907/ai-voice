import { Injectable, NotFoundException, BadRequestException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { LearningProposal } from './learning-proposal.entity'
import { CreateProposalDto } from './dto/create-proposal.dto'

@Injectable()
export class LearningService {
  constructor(
    @InjectRepository(LearningProposal)
    private readonly proposalRepo: Repository<LearningProposal>,
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
    const qb = this.proposalRepo
      .createQueryBuilder('lp')
      .orderBy('lp.createdAt', 'DESC')
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
}
