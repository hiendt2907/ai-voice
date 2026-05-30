import { IsString, IsNumber, IsOptional, IsBoolean, Min, Max, IsArray, IsIn } from 'class-validator'

export class UpsertVoiceProfileDto {
  @IsString()
  displayName: string

  @IsOptional()
  @IsIn(['male', 'female'])
  gender?: string

  @IsOptional()
  @IsString()
  region?: string

  @IsOptional()
  @IsString()
  ttsEngine?: string

  @IsOptional()
  @IsString()
  ttsVoiceId?: string

  @IsOptional()
  @IsString()
  elevenlabsVoiceId?: string

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  stabilityFactor?: number

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  similarityBoost?: number

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  styleExaggeration?: number

  @IsOptional()
  @IsBoolean()
  useSpeakerBoost?: boolean

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  customFillerPool?: string[]
}
