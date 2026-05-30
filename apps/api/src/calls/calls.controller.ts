import {
  Controller,
  Get,
  Post,
  Param,
  Body,
  Query,
  Res,
  UseGuards,
  Request,
  ParseIntPipe,
  DefaultValuePipe,
  NotFoundException,
} from '@nestjs/common'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FastifyReply = any
import { ApiTags, ApiBearerAuth, ApiOperation, ApiQuery } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { CallsService } from './calls.service'
import { CreateQaScoreDto } from './dto/create-qa-score.dto'

interface AuthRequest {
  user: { userId: string }
}

@ApiTags('calls')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('calls')
export class CallsController {
  constructor(private readonly svc: CallsService) {}

  @Get()
  @ApiOperation({ summary: 'List call sessions (paginated)' })
  @ApiQuery({ name: 'page', required: false })
  @ApiQuery({ name: 'limit', required: false })
  @ApiQuery({ name: 'campaignId', required: false })
  listSessions(
    @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
    @Query('campaignId') campaignId?: string,
  ) {
    return this.svc.listSessions({ page, limit, campaignId })
  }

  @Get('active')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'List currently active call sessions' })
  getActiveCalls() {
    return this.svc.getActiveCalls()
  }

  @Get('qa-queue')
  @Roles('admin', 'qa')
  @ApiOperation({ summary: 'List calls pending QA review' })
  listPendingQa() {
    return this.svc.listPendingQa()
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get call session detail' })
  getSession(@Param('id') id: string) {
    return this.svc.getSession(id)
  }

  @Post(':id/qa-scores')
  @Roles('admin', 'qa')
  @ApiOperation({ summary: 'Submit QA score for a call (qa role)' })
  submitQaScore(
    @Param('id') id: string,
    @Body() dto: CreateQaScoreDto,
    @Request() req: AuthRequest,
  ) {
    return this.svc.submitQaScore(id, req.user.userId, dto)
  }

  @Get(':id/qa-scores')
  @ApiOperation({ summary: 'Get QA scores for a call' })
  getQaScores(@Param('id') id: string) {
    return this.svc.getQaScores(id)
  }

  @Get(':id/turns')
  @ApiOperation({ summary: 'Get transcript turns for a call (ordered by seq)' })
  getTurns(@Param('id') id: string) {
    return this.svc.getTurns(id)
  }

  @Get(':id/recording')
  @ApiOperation({ summary: 'Get recording metadata for a call' })
  getRecording(@Param('id') id: string) {
    return this.svc.getRecording(id)
  }

  @Get(':id/recording/stream')
  @ApiOperation({ summary: 'Stream recording audio for a call' })
  async streamRecording(@Param('id') id: string, @Res() reply: FastifyReply) {
    const stream = await this.svc.streamRecording(id)
    if (!stream) throw new NotFoundException('Recording not found or streaming not configured')
    void reply
      .header('Content-Type', stream.contentType)
      .header('Accept-Ranges', 'bytes')
      .send(stream.body)
  }
}
