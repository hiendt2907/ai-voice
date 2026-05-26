import { Controller, Get, Post, Param, Body, UseGuards, Request } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { ScriptsService } from './scripts.service'
import { CreateCampaignDto } from './dto/create-campaign.dto'
import { CreateVersionDto } from './dto/create-version.dto'
import { ValidateScriptDto } from './dto/validate-script.dto'

interface AuthRequest {
  user: { userId: string; role: string }
}

@ApiTags('scripts')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('scripts')
export class ScriptsController {
  constructor(private readonly svc: ScriptsService) {}

  @Post('validate')
  @ApiOperation({ summary: 'Validate script body against lint rules L001-L008 (no save)' })
  validate(@Body() dto: ValidateScriptDto) {
    return this.svc.validate(dto.body)
  }

  @Get()
  @ApiOperation({ summary: 'List all campaigns' })
  listCampaigns() {
    return this.svc.listCampaigns()
  }

  @Post()
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Create a new campaign' })
  createCampaign(@Body() dto: CreateCampaignDto) {
    return this.svc.createCampaign(dto)
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get campaign with all versions' })
  getCampaign(@Param('id') id: string) {
    return this.svc.getCampaign(id)
  }

  @Get(':id/active')
  @ApiOperation({ summary: 'Get active (published) script body for campaign' })
  getActive(@Param('id') id: string) {
    return this.svc.getActiveScript(id)
  }

  @Get(':id/versions')
  @ApiOperation({ summary: 'List all versions for campaign' })
  listVersions(@Param('id') id: string) {
    return this.svc.listVersions(id)
  }

  @Post(':id/versions')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Create a new draft version (validates before saving)' })
  createVersion(
    @Param('id') id: string,
    @Body() dto: CreateVersionDto,
    @Request() req: AuthRequest,
  ) {
    return this.svc.createVersion(id, dto, req.user.userId)
  }

  @Post(':id/versions/:version/submit-review')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Submit draft version for QA review' })
  submitReview(@Param('id') id: string, @Param('version') version: string) {
    return this.svc.submitForReview(id, version)
  }

  @Post(':id/versions/:version/publish')
  @Roles('admin')
  @ApiOperation({ summary: 'Publish a reviewed version (admin only)' })
  publish(@Param('id') id: string, @Param('version') version: string) {
    return this.svc.publishVersion(id, version)
  }
}
