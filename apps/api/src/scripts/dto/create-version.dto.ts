import { IsString, IsNotEmpty, Matches, IsObject } from 'class-validator'
import { ApiProperty } from '@nestjs/swagger'

export class CreateVersionDto {
  @ApiProperty({ example: '1.0.0', description: 'Semver version string' })
  @IsString()
  @IsNotEmpty()
  @Matches(/^\d+\.\d+\.\d+$/, { message: 'version must be semver (e.g. 1.0.0)' })
  version: string

  @ApiProperty({ description: 'Full CallScript body' })
  @IsObject()
  body: Record<string, unknown>
}
