import { IsString, IsOptional, IsArray, IsNumber, IsBoolean, IsUUID, Min, Max } from 'class-validator'

export class UpdateArticleDto {
  @IsString()
  @IsOptional()
  title?: string

  @IsString()
  @IsOptional()
  category?: string

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  tags?: string[]

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  questionVariants?: string[]

  @IsString()
  @IsOptional()
  answerText?: string

  @IsString()
  @IsOptional()
  answerMale?: string

  @IsString()
  @IsOptional()
  answerFemale?: string

  @IsNumber()
  @Min(0)
  @Max(1)
  @IsOptional()
  confidenceThreshold?: number

  @IsBoolean()
  @IsOptional()
  isActive?: boolean

  @IsString()
  @IsOptional()
  embeddingJson?: string

  /** Campaign/script the article is linked to. Used by Script CMS "Gắn đã chọn". */
  @IsUUID()
  @IsOptional()
  scriptId?: string
}
