import { IsString, IsNumber, Min } from 'class-validator'

export class UpsertSttDto {
  @IsString()
  modelSize: string

  @IsString()
  device: string

  @IsString()
  computeType: string

  @IsString()
  language: string

  @IsNumber()
  @Min(100)
  endOfUtteranceSilenceMs: number
}
