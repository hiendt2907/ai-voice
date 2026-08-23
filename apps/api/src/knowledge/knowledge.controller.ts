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
import { KnowledgeService } from './knowledge.service'
import { AuditService } from '../audit/audit.service'
import { CreateArticleDto } from './dto/create-article.dto'
import { UpdateArticleDto } from './dto/update-article.dto'

interface AuthRequest {
  user: { userId: string; email: string; role: string }
}

@ApiTags('knowledge')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('knowledge')
export class KnowledgeController {
  constructor(
    private readonly svc: KnowledgeService,
    private readonly audit: AuditService,
  ) {}

  @Get()
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'List KB articles' })
  @ApiQuery({ name: 'category', required: false })
  @ApiQuery({ name: 'all', required: false, type: Boolean })
  list(@Query('category') category?: string, @Query('all') all?: string) {
    return this.svc.list(category, all !== 'true')
  }

  @Get('rag-export')
  @ApiOperation({ summary: 'Export all active articles with embeddings for voice worker' })
  ragExport() {
    return this.svc.listForRag()
  }

  @Get(':id')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Get KB article by id' })
  get(@Param('id') id: string) {
    return this.svc.get(id)
  }

  @Post()
  @Roles('admin', 'operator', 'qa')
  @ApiOperation({ summary: 'Create KB article' })
  create(@Body() dto: CreateArticleDto, @Request() req: AuthRequest) {
    return this.svc.create(dto, req.user.userId)
  }

  @Patch(':id')
  @Roles('admin', 'operator', 'qa')
  @ApiOperation({ summary: 'Update KB article' })
  async update(@Param('id') id: string, @Body() dto: UpdateArticleDto, @Request() req: AuthRequest) {
    const article = await this.svc.update(id, dto, req.user.userId)
    void this.audit.log({
      actorId: req.user.userId,
      actorEmail: req.user.email,
      action: 'update',
      entity: 'kb_article',
      entityId: id,
      diff: { after: dto },
    })
    return article
  }

  @Delete(':id')
  @Roles('admin')
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Delete KB article' })
  remove(@Param('id') id: string) {
    return this.svc.remove(id)
  }

  @Post('test')
  @ApiOperation({ summary: 'Test KB RAG search — forward query to voice worker' })
  testSearch(@Body() body: { query: string; limit?: number }) {
    return this.svc.testSearch(body.query, body.limit ?? 3)
  }
}
