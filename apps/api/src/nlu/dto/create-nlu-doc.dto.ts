import { IsString, IsIn, IsOptional, IsUUID, IsBoolean, IsObject } from 'class-validator'
import type { NluDocType } from '../nlu-document.entity'

export class CreateNluDocDto {
  @IsIn(['intent', 'filler', 'reprompt', 'dialog_node'])
  type: NluDocType

  @IsString()
  label: string

  @IsString()
  content: string

  @IsOptional()
  @IsObject()
  meta?: Record<string, unknown>

  @IsOptional()
  @IsUUID()
  campaignId?: string

  @IsOptional()
  @IsUUID()
  scriptId?: string

  @IsOptional()
  @IsBoolean()
  isActive?: boolean
}
