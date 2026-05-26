import { IsString, IsIn, IsObject, IsOptional } from 'class-validator'
import { ApiProperty } from '@nestjs/swagger'

export class CreateProposalDto {
  @ApiProperty({ enum: ['new_intent_example', 'edit_variant', 'add_reprompt', 'slot_correction'] })
  @IsIn(['new_intent_example', 'edit_variant', 'add_reprompt', 'slot_correction'])
  type: 'new_intent_example' | 'edit_variant' | 'add_reprompt' | 'slot_correction'

  @ApiProperty()
  @IsObject()
  payload: Record<string, unknown>

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  callSessionId?: string
}
