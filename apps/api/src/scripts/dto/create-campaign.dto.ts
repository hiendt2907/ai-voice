import { IsString, IsNotEmpty, IsIn } from 'class-validator'
import { ApiProperty } from '@nestjs/swagger'

export class CreateCampaignDto {
  @ApiProperty({ example: 'Booking Inbound v1' })
  @IsString()
  @IsNotEmpty()
  name: string

  @ApiProperty({ enum: ['inbound', 'outbound'] })
  @IsIn(['inbound', 'outbound'])
  direction: 'inbound' | 'outbound'

  @ApiProperty({ example: 'linh_clone_v1' })
  @IsString()
  @IsNotEmpty()
  voiceProfile: string
}
