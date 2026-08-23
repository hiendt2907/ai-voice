import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { KnowledgeArticle } from './knowledge-article.entity'
import { KnowledgeService } from './knowledge.service'
import { KnowledgeController } from './knowledge.controller'
import { AuditModule } from '../audit/audit.module'
import { VoiceWorkerUrlModule } from '../common/voice-worker-url.module'

@Module({
  imports: [TypeOrmModule.forFeature([KnowledgeArticle]), AuditModule, VoiceWorkerUrlModule],
  providers: [KnowledgeService],
  controllers: [KnowledgeController],
  exports: [KnowledgeService],
})
export class KnowledgeModule {}
