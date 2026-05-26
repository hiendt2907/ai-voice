import { Controller, Get, Query, UseGuards } from '@nestjs/common'
import { ApiBearerAuth, ApiTags } from '@nestjs/swagger'
import { AuditService } from './audit.service'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'

@ApiTags('audit')
@ApiBearerAuth()
@Controller('audit')
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
export class AuditController {
  constructor(private readonly auditService: AuditService) {}

  @Get()
  findAll(
    @Query('actorId') actorId?: string,
    @Query('entity') entity?: string,
    @Query('action') action?: string,
    @Query('limit') limit = '50',
    @Query('offset') offset = '0',
  ) {
    return this.auditService.findAll({
      actorId,
      entity,
      action,
      limit: parseInt(limit, 10),
      offset: parseInt(offset, 10),
    })
  }
}
