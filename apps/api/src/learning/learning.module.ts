import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { LearningProposal } from './learning-proposal.entity'
import { LearningService } from './learning.service'
import { LearningController } from './learning.controller'

@Module({
  imports: [TypeOrmModule.forFeature([LearningProposal])],
  providers: [LearningService],
  controllers: [LearningController],
})
export class LearningModule {}
