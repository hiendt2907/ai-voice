import { IsBoolean, IsOptional, IsIn, IsArray, IsString } from 'class-validator'

export class PatchCampaignDto {
  @IsOptional()
  @IsBoolean()
  isActive?: boolean

  @IsOptional()
  @IsIn(['shadow', 'medium', 'full'])
  interceptionMode?: 'shadow' | 'medium' | 'full'

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  interceptionDomains?: string[]
}
