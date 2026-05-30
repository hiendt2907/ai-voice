import { IsBoolean, IsOptional } from 'class-validator'

export class PatchCampaignDto {
  @IsOptional()
  @IsBoolean()
  isActive?: boolean
}
