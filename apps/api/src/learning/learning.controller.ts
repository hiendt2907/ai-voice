import { Controller, Get, Post, Param, Body, Query, UseGuards, Request } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation, ApiQuery } from '@nestjs/swagger'
import { IsIn, IsOptional, IsString } from 'class-validator'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { LearningService } from './learning.service'
import { AuditService } from '../audit/audit.service'
import { CreateProposalDto } from './dto/create-proposal.dto'

class ReviewProposalDto {
  @IsIn(['approved', 'rejected'])
  decision: 'approved' | 'rejected'

  @IsOptional()
  @IsString()
  reviewNote?: string
}

interface AuthRequest {
  user: { userId: string; email: string }
}

@ApiTags('learning')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('learning')
export class LearningController {
  constructor(
    private readonly svc: LearningService,
    private readonly audit: AuditService,
  ) {}

  @Post('proposals')
  @Roles('admin', 'qa')
  @ApiOperation({ summary: 'Create a learning proposal' })
  createProposal(@Body() dto: CreateProposalDto) {
    return this.svc.createProposal(dto)
  }

  @Get('proposals')
  @ApiOperation({ summary: 'List learning proposals' })
  @ApiQuery({ name: 'status', required: false, enum: ['pending', 'approved', 'rejected'] })
  listProposals(@Query('status') status?: string) {
    return this.svc.listProposals(status)
  }

  @Post('proposals/:id/review')
  @Roles('admin', 'qa')
  @ApiOperation({ summary: 'Approve or reject a learning proposal (HITL)' })
  async reviewProposal(
    @Param('id') id: string,
    @Body() dto: ReviewProposalDto,
    @Request() req: AuthRequest,
  ) {
    const proposal = await this.svc.reviewProposal(id, dto.decision, req.user.userId, dto.reviewNote)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: `review_${dto.decision}`, entity: 'learning_proposal', entityId: id, diff: { after: { decision: dto.decision, note: dto.reviewNote } } })
    return proposal
  }

  @Post('proposals/:id/apply')
  @Roles('admin')
  @ApiOperation({ summary: 'Apply an approved proposal — creates a new draft version' })
  async applyProposal(@Param('id') id: string, @Request() req: AuthRequest) {
    const version = await this.svc.applyProposal(id, req.user.userId)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'apply_proposal', entity: 'learning_proposal', entityId: id, diff: { after: { resultVersionId: version.scriptVersion.id } } })
    return version
  }
}
