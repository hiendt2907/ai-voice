import { IsString } from 'class-validator'

export class UpsertCloudFoneDto {
  @IsString()
  socket: string

  @IsString()
  port: string

  @IsString()
  realm: string

  @IsString()
  user: string

  @IsString()
  password: string
}
