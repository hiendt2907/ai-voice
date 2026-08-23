import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { Campaign } from './campaign.entity'
import { ScriptVersion } from './script-version.entity'
import { VoiceProfile } from './voice-profile.entity'
import { HotlineRoute } from './hotline-route.entity'
import { KnowledgeArticle } from '../knowledge/knowledge-article.entity'
import { NluDocument } from '../nlu/nlu-document.entity'
import { ScriptLintService } from './lint/script-lint.service'
import { ScriptsService } from './scripts.service'
import { ScriptsController } from './scripts.controller'
import { AuditModule } from '../audit/audit.module'
import { VoiceWorkerUrlModule } from '../common/voice-worker-url.module'

@Module({
  imports: [
    TypeOrmModule.forFeature([Campaign, ScriptVersion, VoiceProfile, HotlineRoute, KnowledgeArticle, NluDocument]),
    AuditModule,
    VoiceWorkerUrlModule,
  ],
  providers: [ScriptLintService, ScriptsService],
  controllers: [ScriptsController],
  exports: [ScriptsService],
})
export class ScriptsModule {}
