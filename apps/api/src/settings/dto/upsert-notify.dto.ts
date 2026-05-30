import { IsString, IsNumber, Min } from 'class-validator'

export class UpsertNotifyDto {
  @IsString()
  platform: string

  @IsString()
  teamsWebhookUrl: string

  @IsString()
  telegramBotToken: string

  @IsString()
  telegramGroupId: string

  @IsNumber()
  @Min(30)
  questionTimeoutSeconds: number

  @IsNumber()
  @Min(1)
  callbackDelayMinutes: number
}
