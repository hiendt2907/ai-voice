import { Controller, Get, Query, Res, UseGuards } from '@nestjs/common'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FastifyReply = any
import { ApiTags, ApiBearerAuth, ApiOperation, ApiQuery } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { AnalyticsService } from './analytics.service'

@ApiTags('analytics')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('analytics')
export class AnalyticsController {
  constructor(private readonly svc: AnalyticsService) {}

  @Get('overview')
  @ApiOperation({ summary: 'Dashboard KPI overview' })
  getOverview() {
    return this.svc.getOverview()
  }

  @Get('calls-by-day')
  @ApiOperation({ summary: 'Calls grouped by day' })
  @ApiQuery({ name: 'from', required: false, description: 'YYYY-MM-DD start date' })
  @ApiQuery({ name: 'to', required: false, description: 'YYYY-MM-DD end date' })
  getCallsByDay(@Query('from') from?: string, @Query('to') to?: string) {
    return this.svc.getCallsByDay(from, to)
  }

  @Get('qa-trends')
  @ApiOperation({ summary: 'QA score trends by week' })
  @ApiQuery({ name: 'from', required: false })
  @ApiQuery({ name: 'to', required: false })
  getQaTrends(@Query('from') from?: string, @Query('to') to?: string) {
    return this.svc.getQaTrends(from, to)
  }

  @Get('duration')
  @ApiOperation({ summary: 'Average call duration by campaign + status' })
  @ApiQuery({ name: 'from', required: false })
  @ApiQuery({ name: 'to', required: false })
  getDurationStats(@Query('from') from?: string, @Query('to') to?: string) {
    return this.svc.getDurationStats(from, to)
  }

  @Get('elevenlabs')
  @ApiOperation({ summary: 'ElevenLabs API request metrics from Redis' })
  getElevenLabsMetrics() {
    return this.svc.getElevenLabsMetrics()
  }

  @Get('export')
  @ApiOperation({ summary: 'Export analytics as XLSX' })
  @ApiQuery({ name: 'from', required: false })
  @ApiQuery({ name: 'to', required: false })
  async exportXlsx(
    @Query('from') from: string | undefined,
    @Query('to') to: string | undefined,
    @Res() res: FastifyReply,
  ) {
    const buffer = await this.svc.exportXlsx(from, to)
    const fromStr = from ?? 'all'
    const toStr = to ?? 'all'
    void res
      .header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      .header('Content-Disposition', `attachment; filename="analytics_${fromStr}_${toStr}.xlsx"`)
      .send(buffer)
  }
}
