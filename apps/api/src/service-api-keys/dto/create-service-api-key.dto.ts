import { IsString, MinLength, MaxLength } from 'class-validator'

export class CreateServiceApiKeyDto {
  @IsString()
  @MinLength(3)
  @MaxLength(80)
  name: string
}
