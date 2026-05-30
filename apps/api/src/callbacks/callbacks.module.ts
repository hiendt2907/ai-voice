import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { CallbackRequest } from './callback-request.entity'
import { CallbacksService } from './callbacks.service'
import { CallbacksController } from './callbacks.controller'

@Module({
  imports: [TypeOrmModule.forFeature([CallbackRequest])],
  controllers: [CallbacksController],
  providers: [CallbacksService],
  exports: [CallbacksService],
})
export class CallbacksModule {}
