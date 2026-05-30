import { IsString, IsOptional, IsArray, IsNumber, IsBoolean, IsUUID, Min, Max } from 'class-validator'

export class CreateArticleDto {
  @IsString()
  title: string

  @IsString()
  @IsOptional()
  category?: string

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  tags?: string[]

  @IsArray()
  @IsString({ each: true })
  questionVariants: string[]

  @IsString()
  answerText: string

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

  @IsUUID()
  @IsOptional()
  scriptId?: string
}
