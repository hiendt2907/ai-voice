import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { NluDocument } from './nlu-document.entity'
import { NluService } from './nlu.service'
import { NluController } from './nlu.controller'
import { AuditModule } from '../audit/audit.module'
import { VoiceWorkerUrlModule } from '../common/voice-worker-url.module'

@Module({
  imports: [TypeOrmModule.forFeature([NluDocument]), AuditModule, VoiceWorkerUrlModule],
  controllers: [NluController],
  providers: [NluService],
  exports: [NluService],
})
export class NluModule {}
