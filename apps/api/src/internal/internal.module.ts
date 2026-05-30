import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { ServiceApiKey } from './service-api-key.entity'
import { InternalController } from './internal.controller'
import { CallsModule } from '../calls/calls.module'
import { CallbacksModule } from '../callbacks/callbacks.module'
import { SettingsModule } from '../settings/settings.module'
import { KnowledgeModule } from '../knowledge/knowledge.module'
import { LearningModule } from '../learning/learning.module'
import { NluModule } from '../nlu/nlu.module'

@Module({
  imports: [TypeOrmModule.forFeature([ServiceApiKey]), CallsModule, CallbacksModule, SettingsModule, KnowledgeModule, LearningModule, NluModule],
  controllers: [InternalController],
})
export class InternalModule {}
