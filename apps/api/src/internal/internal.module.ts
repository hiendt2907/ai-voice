import { Module } from '@nestjs/common'
import { InternalController } from './internal.controller'
import { CallsModule } from '../calls/calls.module'

@Module({
  imports: [CallsModule],
  controllers: [InternalController],
})
export class InternalModule {}
