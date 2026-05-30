import { IsString, IsNumber, IsOptional, Min, Max } from 'class-validator'

export class UpsertTtsDto {
  @IsString()
  engine: string

  @IsString()
  voice: string

  @IsNumber()
  @Min(8000)
  sampleRate: number

  @IsNumber()
  @Min(0.5)
  @Max(2.0)
  speedFactor: number

  @IsOptional()
  @IsString()
  elevenlabsApiKey?: string

  @IsOptional()
  @IsString()
  elevenlabsVoiceId?: string

  @IsOptional()
  @IsString()
  elevenlabsModelId?: string

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  elevenlabsStability?: number

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  elevenlabsSimilarityBoost?: number

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  elevenlabsStyleExaggeration?: number

  @IsOptional()
  elevenlabsUseSpeakerBoost?: boolean
}
