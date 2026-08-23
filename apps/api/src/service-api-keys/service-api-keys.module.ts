import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { ServiceApiKey } from '../internal/service-api-key.entity'
import { ServiceApiKeysController } from './service-api-keys.controller'
import { ServiceApiKeysService } from './service-api-keys.service'
import { AuditModule } from '../audit/audit.module'

@Module({
  imports: [TypeOrmModule.forFeature([ServiceApiKey]), AuditModule],
  controllers: [ServiceApiKeysController],
  providers: [ServiceApiKeysService],
})
export class ServiceApiKeysModule {}
