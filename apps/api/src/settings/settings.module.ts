import { Module } from '@nestjs/common'
import { TypeOrmModule } from '@nestjs/typeorm'
import { CloudFoneSettings } from './cloudfone-settings.entity'
import { SettingsService } from './settings.service'
import { SettingsController } from './settings.controller'

@Module({
  imports: [TypeOrmModule.forFeature([CloudFoneSettings])],
  providers: [SettingsService],
  controllers: [SettingsController],
  exports: [SettingsService],
})
export class SettingsModule {}
