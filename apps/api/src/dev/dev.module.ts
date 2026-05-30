import { Module } from '@nestjs/common'
import { KnowledgeModule } from '../knowledge/knowledge.module'
import { NluModule } from '../nlu/nlu.module'
import { DevController } from './dev.controller'

@Module({ imports: [KnowledgeModule, NluModule], controllers: [DevController] })
export class DevModule {}
