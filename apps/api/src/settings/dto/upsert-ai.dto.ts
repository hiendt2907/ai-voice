import { IsString, IsNumber, IsBoolean, Min } from 'class-validator'

export class UpsertAiDto {
  @IsString()
  ollamaBaseUrl: string

  @IsString()
  ollamaModel: string

  @IsNumber()
  @Min(100)
  nluTimeoutMs: number

  @IsNumber()
  @Min(100)
  responseTimeoutMs: number

  @IsBoolean()
  fallbackToSubstring: boolean
}
