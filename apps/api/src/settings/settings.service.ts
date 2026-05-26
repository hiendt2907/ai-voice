import { Injectable } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { CloudFoneSettings } from './cloudfone-settings.entity'
import { UpsertCloudFoneDto } from './dto/upsert-cloudfone.dto'

const DEFAULT_ID = 'default'

@Injectable()
export class SettingsService {
  constructor(
    @InjectRepository(CloudFoneSettings)
    private readonly repo: Repository<CloudFoneSettings>,
  ) {}

  async getCloudFone(): Promise<CloudFoneSettings> {
    const row = await this.repo.findOne({ where: { id: DEFAULT_ID } })
    if (!row) return this.repo.create({ id: DEFAULT_ID, odsUrl: '', apiKey: '', tenantId: '' })
    return row
  }

  async upsertCloudFone(dto: UpsertCloudFoneDto, updatedBy: string): Promise<CloudFoneSettings> {
    return this.repo.save({ id: DEFAULT_ID, ...dto, updatedBy })
  }
}
