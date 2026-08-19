import { IsBoolean, IsString, IsInt, IsNumber, Min, Max, MaxLength } from 'class-validator'

export class UpsertConversationDto {
  @IsBoolean()
  enabled: boolean

  @IsString()
  ollamaModel: string

  @IsString()
  @MaxLength(4000)
  systemPrompt: string

  @IsInt()
  @Min(1)
  @Max(20)
  maxHistoryTurns: number

  @IsNumber()
  @Min(0.0)
  @Max(1.0)
  temperature: number

  @IsBoolean()
  sentimentEnabled: boolean

  @IsBoolean()
  kbGroundingEnabled: boolean

  @IsInt()
  @Min(10)
  @Max(200)
  sentenceSplitMinChars: number
}
