import { Controller, Get, Put, Body, UseGuards, Request } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { SettingsService } from './settings.service'
import { UpsertCloudFoneDto } from './dto/upsert-cloudfone.dto'

interface AuthRequest {
  user: { userId: string }
}

@ApiTags('settings')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('settings')
export class SettingsController {
  constructor(private readonly svc: SettingsService) {}

  @Get('cloudfone')
  @ApiOperation({ summary: 'Get CloudFone connection settings' })
  getCloudFone() {
    return this.svc.getCloudFone()
  }

  @Put('cloudfone')
  @Roles('admin')
  @ApiOperation({ summary: 'Update CloudFone connection settings (admin only)' })
  upsertCloudFone(@Body() dto: UpsertCloudFoneDto, @Request() req: AuthRequest) {
    return this.svc.upsertCloudFone(dto, req.user.userId)
  }
}
