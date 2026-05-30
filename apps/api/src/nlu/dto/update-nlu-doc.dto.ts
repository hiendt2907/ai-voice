import { IsString, IsOptional, IsBoolean, IsObject, IsUUID } from 'class-validator'

export class UpdateNluDocDto {
  @IsOptional()
  @IsString()
  label?: string

  @IsOptional()
  @IsString()
  content?: string

  @IsOptional()
  @IsObject()
  meta?: Record<string, unknown>

  @IsOptional()
  @IsBoolean()
  isActive?: boolean

  /** Campaign/script the doc is linked to. Used by Script CMS "Gắn đã chọn". */
  @IsOptional()
  @IsUUID()
  scriptId?: string
}
