import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { ServiceApiKey } from './service-api-key.entity'
import { InternalController } from './internal.controller'
import { InternalAuthGuard } from './internal-auth.guard'
import { CallsModule } from '../calls/calls.module'
import { CallbacksModule } from '../callbacks/callbacks.module'
import { SettingsModule } from '../settings/settings.module'
import { KnowledgeModule } from '../knowledge/knowledge.module'
import { LearningModule } from '../learning/learning.module'
import { NluModule } from '../nlu/nlu.module'
import { ScriptsModule } from '../scripts/scripts.module'

@Module({
  imports: [TypeOrmModule.forFeature([ServiceApiKey]), CallsModule, CallbacksModule, SettingsModule, KnowledgeModule, LearningModule, NluModule, ScriptsModule],
  controllers: [InternalController],
  providers: [InternalAuthGuard],
})
export class InternalModule {}
