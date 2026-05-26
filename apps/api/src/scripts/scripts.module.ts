import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { Campaign } from './campaign.entity'
import { ScriptVersion } from './script-version.entity'
import { ScriptLintService } from './lint/script-lint.service'
import { ScriptsService } from './scripts.service'
import { ScriptsController } from './scripts.controller'

@Module({
  imports: [TypeOrmModule.forFeature([Campaign, ScriptVersion])],
  providers: [ScriptLintService, ScriptsService],
  controllers: [ScriptsController],
  exports: [ScriptsService],
})
export class ScriptsModule {}
