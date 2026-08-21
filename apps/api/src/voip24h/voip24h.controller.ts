import { Controller, Post, Body, UseGuards, Request } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { AuditService } from '../audit/audit.service'
import { Voip24hService } from './voip24h.service'
import { DialDto } from './dto/dial.dto'

interface AuthRequest {
  user: { userId: string; email: string; role: string }
}

@ApiTags('voip24h')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('voip24h')
export class Voip24hController {
  constructor(
    private readonly svc: Voip24hService,
    private readonly audit: AuditService,
  ) {}

  @Post('dial')
  @Roles('admin', 'operator', 'qa')
  @ApiOperation({ summary: 'Place a real outbound call via voip24h to the given phone number (test calling)' })
  async dial(@Body() dto: DialDto, @Request() req: AuthRequest) {
    const result = await this.svc.dial(dto.phone)
    void this.audit.log({
      actorId: req.user.userId,
      actorEmail: req.user.email,
      action: 'dial',
      entity: 'voip24h_call',
      entityId: dto.phone,
      diff: { after: { phone: dto.phone } },
    })
    return result
  }
}
