import {
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Param,
  Body,
  Query,
  UseGuards,
  Request,
  HttpCode,
  HttpStatus,
} from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation, ApiQuery } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { NluService } from './nlu.service'
import { AuditService } from '../audit/audit.service'
import { CreateNluDocDto } from './dto/create-nlu-doc.dto'
import { UpdateNluDocDto } from './dto/update-nlu-doc.dto'
import type { NluDocType } from './nlu-document.entity'

interface AuthRequest {
  user: { userId: string; email: string; role: string }
}

@ApiTags('nlu')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('nlu')
export class NluController {
  constructor(
    private readonly svc: NluService,
    private readonly audit: AuditService,
  ) {}

  @Get('documents')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'List NLU documents' })
  @ApiQuery({ name: 'type', required: false, enum: ['intent', 'filler', 'reprompt', 'dialog_node'] })
  @ApiQuery({ name: 'campaignId', required: false })
  @ApiQuery({ name: 'scriptId', required: false })
  @ApiQuery({ name: 'all', required: false, type: Boolean })
  list(
    @Query('type') type?: NluDocType,
    @Query('campaignId') campaignId?: string,
    @Query('all') all?: string,
    @Query('scriptId') scriptId?: string,
  ) {
    return this.svc.list(type, campaignId, all !== 'true', scriptId)
  }

  @Get('documents/:id')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Get NLU document by id' })
  get(@Param('id') id: string) {
    return this.svc.get(id)
  }

  @Post('documents')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Create NLU document' })
  create(@Body() dto: CreateNluDocDto) {
    return this.svc.create(dto)
  }

  @Patch('documents/:id')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Update NLU document' })
  async update(@Param('id') id: string, @Body() dto: UpdateNluDocDto, @Request() req: AuthRequest) {
    const doc = await this.svc.update(id, dto)
    void this.audit.log({
      actorId: req.user.userId,
      actorEmail: req.user.email,
      action: 'update',
      entity: 'nlu_document',
      entityId: id,
      diff: { after: dto },
    })
    return doc
  }

  @Delete('documents/:id')
  @Roles('admin')
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Delete NLU document' })
  remove(@Param('id') id: string) {
    return this.svc.remove(id)
  }
}
