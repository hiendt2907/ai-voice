import { Controller, Post, Body } from '@nestjs/common'
import { ApiTags, ApiOperation } from '@nestjs/swagger'
import { IsString, IsOptional, IsArray, IsNumber, IsObject, IsIn } from 'class-validator'
import { CallsService } from '../calls/calls.service'

class CallEndedDto {
  @IsString()
  sessionId: string

  @IsOptional()
  @IsString()
  campaignId?: string

  @IsOptional()
  @IsString()
  scriptVersionId?: string

  @IsOptional()
  @IsIn(['inbound', 'outbound'])
  direction?: 'inbound' | 'outbound'

  @IsOptional()
  @IsString()
  callerNumber?: string

  @IsIn(['completed', 'handoff', 'error'])
  status: 'completed' | 'handoff' | 'error'

  @IsOptional()
  @IsArray()
  transcript?: Record<string, unknown>[]

  @IsOptional()
  @IsObject()
  slots?: Record<string, string>

  @IsOptional()
  @IsString()
  finalStepId?: string

  @IsOptional()
  @IsNumber()
  durationSeconds?: number

  @IsOptional()
  @IsString()
  startedAt?: string

  @IsOptional()
  @IsString()
  endedAt?: string
}

@ApiTags('internal')
@Controller('internal')
export class InternalController {
  constructor(private readonly callsService: CallsService) {}

  @Post('call-events')
  @ApiOperation({ summary: 'Voice worker webhook — call ended event' })
  async handleCallEvent(@Body() dto: CallEndedDto) {
    const session = await this.callsService.handleCallEnded(dto)
    return { ok: true, id: session.id }
  }
}
