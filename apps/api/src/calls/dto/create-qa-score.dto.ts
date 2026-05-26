import { IsInt, IsOptional, IsString, IsArray, Max, Min } from 'class-validator'
import { ApiProperty } from '@nestjs/swagger'

export class CreateQaScoreDto {
  @ApiProperty({ minimum: 0, maximum: 5 })
  @IsInt()
  @Min(0)
  @Max(5)
  score: number

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  notes?: string

  @ApiProperty({ type: [String], required: false })
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  tags?: string[]
}
