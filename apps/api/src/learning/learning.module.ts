import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { LearningProposal } from './learning-proposal.entity'
import { LearningApplication } from './learning-application.entity'
import { LearningService } from './learning.service'
import { LearningController } from './learning.controller'
import { ScriptsModule } from '../scripts/scripts.module'
import { AuditModule } from '../audit/audit.module'

@Module({
  imports: [TypeOrmModule.forFeature([LearningProposal, LearningApplication]), ScriptsModule, AuditModule],
  providers: [LearningService],
  controllers: [LearningController],
  exports: [LearningService],
})
export class LearningModule {}
