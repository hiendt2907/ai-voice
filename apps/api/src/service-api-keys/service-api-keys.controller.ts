import { Controller, Get, Post, Patch, Param, Body, UseGuards, Request, ParseUUIDPipe } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { ServiceApiKeysService } from './service-api-keys.service'
import { AuditService } from '../audit/audit.service'
import { CreateServiceApiKeyDto } from './dto/create-service-api-key.dto'

interface AuthRequest {
  user: { userId: string; email: string }
}

/**
 * Quản trị ServiceApiKey — key dùng để xác thực lời gọi service-to-service
 * (voice worker ⇄ NestJS) vào `/internal/*` (xem InternalAuthGuard).
 *
 * CỐ Ý đặt route riêng, KHÔNG nằm dưới `/internal` — ingress
 * (deploy/k8s/api/ingress.yaml) chặn cứng mọi request internet vào
 * `/api/v1/internal`, kể cả từ admin đăng nhập qua Portal. Route quản trị
 * này cần vào được từ trình duyệt nên phải nằm ngoài path bị chặn đó, và tự
 * bảo vệ bằng JwtAuthGuard + @Roles('admin') như mọi trang admin khác thay
 * vì dựa vào lớp chặn ingress.
 */
@ApiTags('service-api-keys')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('service-api-keys')
export class ServiceApiKeysController {
  constructor(
    private readonly svc: ServiceApiKeysService,
    private readonly audit: AuditService,
  ) {}

  @Get()
  @Roles('admin')
  @ApiOperation({ summary: 'List service API keys (không bao giờ trả plaintext hay hash)' })
  list() {
    return this.svc.list()
  }

  @Post()
  @Roles('admin')
  @ApiOperation({
    summary: 'Tạo service API key mới. Giá trị plaintext chỉ được trả về đúng MỘT LẦN trong response này.',
  })
  async create(@Body() dto: CreateServiceApiKeyDto, @Request() req: AuthRequest) {
    const created = await this.svc.create(dto.name)
    void this.audit.log({
      actorId: req.user.userId,
      actorEmail: req.user.email,
      action: 'create',
      entity: 'service_api_key',
      entityId: created.id,
      diff: { after: { name: created.name, isActive: created.isActive } },
    })
    return created
  }

  @Patch(':id/revoke')
  @Roles('admin')
  @ApiOperation({ summary: 'Thu hồi một service API key (soft-delete, giữ lịch sử audit)' })
  async revoke(@Param('id', ParseUUIDPipe) id: string, @Request() req: AuthRequest) {
    const revoked = await this.svc.revoke(id)
    void this.audit.log({
      actorId: req.user.userId,
      actorEmail: req.user.email,
      action: 'revoke',
      entity: 'service_api_key',
      entityId: id,
      diff: { after: { isActive: false } },
    })
    return revoked
  }
}
