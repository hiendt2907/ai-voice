import { IsString, IsNumber, Min } from 'class-validator'

export class UpsertVoiceWorkerDto {
  @IsString()
  internalUrl: string

  @IsNumber()
  @Min(1)
  maxConcurrentSessions: number

  @IsNumber()
  @Min(60)
  sessionCacheTtlSeconds: number
}
