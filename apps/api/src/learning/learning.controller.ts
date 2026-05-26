import { Controller, Get, Post, Param, Body, Query, UseGuards, Request } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation, ApiQuery } from '@nestjs/swagger'
import { IsIn, IsOptional, IsString } from 'class-validator'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { LearningService } from './learning.service'
import { CreateProposalDto } from './dto/create-proposal.dto'

class ReviewProposalDto {
  @IsIn(['approved', 'rejected'])
  decision: 'approved' | 'rejected'

  @IsOptional()
  @IsString()
  reviewNote?: string
}

interface AuthRequest {
  user: { userId: string }
}

@ApiTags('learning')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('learning')
export class LearningController {
  constructor(private readonly svc: LearningService) {}

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
  reviewProposal(
    @Param('id') id: string,
    @Body() dto: ReviewProposalDto,
    @Request() req: AuthRequest,
  ) {
    return this.svc.reviewProposal(id, dto.decision, req.user.userId, dto.reviewNote)
  }
}
