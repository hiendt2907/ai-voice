import { IsObject } from 'class-validator'
import { ApiProperty } from '@nestjs/swagger'

export class ValidateScriptDto {
  @ApiProperty({ description: 'CallScript body to validate against lint rules L001-L008' })
  @IsObject()
  body: Record<string, unknown>
}
