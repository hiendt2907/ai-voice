import { IsString } from 'class-validator'

export class UpsertCloudFoneDto {
  @IsString()
  odsUrl: string

  @IsString()
  apiKey: string

  @IsString()
  tenantId: string
}
