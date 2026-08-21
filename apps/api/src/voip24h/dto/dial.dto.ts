import { IsString, Matches } from 'class-validator'
import { ApiProperty } from '@nestjs/swagger'

export class DialDto {
  @ApiProperty({ example: '0901234567', description: 'Vietnamese phone number to dial' })
  @IsString()
  @Matches(/^(0|\+84)\d{9,10}$/, { message: 'phone must be a valid Vietnamese phone number' })
  phone: string
}
