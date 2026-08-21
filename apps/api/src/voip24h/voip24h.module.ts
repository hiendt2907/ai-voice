import { Module } from '@nestjs/common'
import { Voip24hService } from './voip24h.service'
import { Voip24hController } from './voip24h.controller'
import { AuditModule } from '../audit/audit.module'

@Module({
  imports: [AuditModule],
  providers: [Voip24hService],
  controllers: [Voip24hController],
  exports: [Voip24hService],
})
export class Voip24hModule {}
