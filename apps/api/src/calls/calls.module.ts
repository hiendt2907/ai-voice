import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { CallSession } from './call-session.entity'
import { QaScore } from './qa-score.entity'
import { CallsService } from './calls.service'
import { CallsController } from './calls.controller'

@Module({
  imports: [TypeOrmModule.forFeature([CallSession, QaScore])],
  providers: [CallsService],
  controllers: [CallsController],
  exports: [CallsService],
})
export class CallsModule {}
