import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { VoiceWorkerSettings } from '../settings/voice-worker-settings.entity'
import { VoiceWorkerUrlResolver } from './voice-worker-url.resolver'

/**
 * Cung cấp `VoiceWorkerUrlResolver` cho các module cần gọi voice worker mà
 * không thuộc module settings — xem docstring của resolver để biết thứ tự
 * ưu tiên (DB -> env -> localhost).
 */
@Module({
  imports: [TypeOrmModule.forFeature([VoiceWorkerSettings])],
  providers: [VoiceWorkerUrlResolver],
  exports: [VoiceWorkerUrlResolver],
})
export class VoiceWorkerUrlModule {}
