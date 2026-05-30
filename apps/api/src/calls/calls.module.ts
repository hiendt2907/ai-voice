import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { CallSession } from './call-session.entity'
import { QaScore } from './qa-score.entity'
import { CallTurn } from './call-turn.entity'
import { CallRecording } from './call-recording.entity'
import { CallMetrics } from './call-metrics.entity'
import { CallsService } from './calls.service'
import { CallsController } from './calls.controller'

@Module({
  imports: [TypeOrmModule.forFeature([CallSession, QaScore, CallTurn, CallRecording, CallMetrics])],
  providers: [CallsService],
  controllers: [CallsController],
  exports: [CallsService],
})
export class CallsModule {}
