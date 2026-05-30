import { Controller, Get, Patch, Param, UseGuards } from '@nestjs/common'
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { CallbacksService } from './callbacks.service'
import { CallbackRequest } from './callback-request.entity'

@ApiTags('callbacks')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('callbacks')
export class CallbacksController {
  constructor(private readonly callbacksService: CallbacksService) {}

  @Get()
  @ApiOperation({ summary: 'List all callback requests' })
  listAll(): Promise<CallbackRequest[]> {
    return this.callbacksService.listAll()
  }

  @Get('pending')
  @ApiOperation({ summary: 'List pending callback requests' })
  listPending(): Promise<CallbackRequest[]> {
    return this.callbacksService.listPending()
  }

  @Patch(':id/complete')
  @ApiOperation({ summary: 'Mark a callback request as completed' })
  complete(@Param('id') id: string): Promise<CallbackRequest> {
    return this.callbacksService.markCompleted(id)
  }
}
