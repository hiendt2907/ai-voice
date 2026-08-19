import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { CloudFoneSettings } from './cloudfone-settings.entity'
import { AiSettings } from './ai-settings.entity'
import { SttSettings } from './stt-settings.entity'
import { TtsSettings } from './tts-settings.entity'
import { NotifySettings } from './notify-settings.entity'
import { VoiceWorkerSettings } from './voice-worker-settings.entity'
import { DoctorCheckSettings } from './doctorcheck-settings.entity'
import { ConversationSettings } from './conversation-settings.entity'
import { SettingsService } from './settings.service'
import { SettingsController } from './settings.controller'
import { AuditModule } from '../audit/audit.module'

@Module({
  imports: [
    TypeOrmModule.forFeature([
      CloudFoneSettings,
      AiSettings,
      SttSettings,
      TtsSettings,
      NotifySettings,
      VoiceWorkerSettings,
      DoctorCheckSettings,
      ConversationSettings,
    ]),
    AuditModule,
  ],
  providers: [SettingsService],
  controllers: [SettingsController],
  exports: [SettingsService],
})
export class SettingsModule {}
