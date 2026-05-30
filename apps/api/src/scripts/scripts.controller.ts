import { Controller, Get, Post, Put, Patch, Delete, Param, Body, UseGuards, Request, HttpCode } from '@nestjs/common'
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger'
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard'
import { RolesGuard } from '../auth/guards/roles.guard'
import { Roles } from '../auth/decorators/roles.decorator'
import { ScriptsService } from './scripts.service'
import { AuditService } from '../audit/audit.service'
import { CreateCampaignDto } from './dto/create-campaign.dto'
import { CreateVersionDto } from './dto/create-version.dto'
import { ValidateScriptDto } from './dto/validate-script.dto'
import { PatchCampaignDto } from './dto/patch-campaign.dto'
import { UpsertVoiceProfileDto } from './dto/upsert-voice-profile.dto'

interface AuthRequest {
  user: { userId: string; email: string; role: string }
}

@ApiTags('scripts')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('scripts')
export class ScriptsController {
  constructor(
    private readonly svc: ScriptsService,
    private readonly audit: AuditService,
  ) {}

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
  async createCampaign(@Body() dto: CreateCampaignDto, @Request() req: AuthRequest) {
    const campaign = await this.svc.createCampaign(dto)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'create', entity: 'campaign', entityId: campaign.id, diff: { after: { name: campaign.name } } })
    return campaign
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get campaign with all versions' })
  getCampaign(@Param('id') id: string) {
    return this.svc.getCampaign(id)
  }

  @Get(':id/related')
  @ApiOperation({ summary: 'Get KB articles and NLU docs related to this script' })
  getRelated(@Param('id') id: string) {
    return this.svc.getRelated(id)
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
  async createVersion(
    @Param('id') id: string,
    @Body() dto: CreateVersionDto,
    @Request() req: AuthRequest,
  ) {
    const version = await this.svc.createVersion(id, dto, req.user.userId)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'create', entity: 'script_version', entityId: version.id, diff: { after: { version: version.version, status: version.status } } })
    return version
  }

  @Post(':id/versions/:version/submit-review')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Submit draft version for QA review' })
  async submitReview(
    @Param('id') id: string,
    @Param('version') version: string,
    @Request() req: AuthRequest,
  ) {
    const sv = await this.svc.submitForReview(id, version)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'submit_review', entity: 'script_version', entityId: sv.id, diff: { after: { status: 'under_review' } } })
    return sv
  }

  @Post(':id/versions/:version/publish')
  @Roles('admin')
  @ApiOperation({ summary: 'Publish a reviewed version (admin only)' })
  async publish(
    @Param('id') id: string,
    @Param('version') version: string,
    @Request() req: AuthRequest,
  ) {
    const sv = await this.svc.publishVersion(id, version)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'publish', entity: 'script_version', entityId: sv.id, diff: { after: { version: sv.version, campaignId: id } } })
    return sv
  }

  @Delete(':id')
  @Roles('admin')
  @HttpCode(204)
  @ApiOperation({ summary: 'Delete campaign and all its versions (admin only)' })
  async deleteCampaign(@Param('id') id: string, @Request() req: AuthRequest) {
    await this.svc.deleteCampaign(id)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'delete', entity: 'campaign', entityId: id, diff: {} })
  }

  @Patch(':id')
  @Roles('admin', 'operator')
  @ApiOperation({ summary: 'Patch campaign (toggle isActive)' })
  async patchCampaign(
    @Param('id') id: string,
    @Body() dto: PatchCampaignDto,
    @Request() req: AuthRequest,
  ) {
    const campaign = await this.svc.patchCampaign(id, dto)
    void this.audit.log({ actorId: req.user.userId, actorEmail: req.user.email, action: 'update', entity: 'campaign', entityId: id, diff: { after: dto } })
    return campaign
  }

  // ── Voice Profiles ────────────────────────────────────────────────────────

  @Get('voice-profiles')
  @ApiOperation({ summary: 'List active voice profiles' })
  listVoiceProfiles() {
    return this.svc.listVoiceProfiles()
  }

  @Get('voice-profiles/:id')
  @ApiOperation({ summary: 'Get voice profile by id' })
  getVoiceProfile(@Param('id') id: string) {
    return this.svc.getVoiceProfile(id)
  }

  @Post('voice-profiles')
  @Roles('admin')
  @ApiOperation({ summary: 'Create voice profile (admin only)' })
  createVoiceProfile(@Body() dto: UpsertVoiceProfileDto) {
    return this.svc.createVoiceProfile(dto)
  }

  @Put('voice-profiles/:id')
  @Roles('admin')
  @ApiOperation({ summary: 'Update voice profile (admin only)' })
  updateVoiceProfile(@Param('id') id: string, @Body() dto: UpsertVoiceProfileDto) {
    return this.svc.updateVoiceProfile(id, dto)
  }

  @Delete('voice-profiles/:id')
  @Roles('admin')
  @HttpCode(204)
  @ApiOperation({ summary: 'Deactivate voice profile (admin only)' })
  deactivateVoiceProfile(@Param('id') id: string) {
    return this.svc.deactivateVoiceProfile(id)
  }
}
