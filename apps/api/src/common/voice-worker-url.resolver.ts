import { Injectable } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { ConfigService } from '@nestjs/config'
import { Repository } from 'typeorm'
import { VoiceWorkerSettings } from '../settings/voice-worker-settings.entity'

const DEFAULT_ID = 'default'
const FALLBACK_URL = 'http://localhost:8000'

/**
 * Nguồn duy nhất xác định base URL của voice worker cho các service KHÔNG
 * thuộc module settings (nlu.service.ts, knowledge.service.ts,
 * scripts.service.ts, ...). Thứ tự ưu tiên khớp với
 * `SettingsService.getVoiceWorkerBaseUrl()`:
 *
 *   1. Bảng `voice_worker_settings.internalUrl` — admin cấu hình qua Portal
 *   2. Biến môi trường `VOICE_WORKER_URL` — sẵn có trong pod
 *   3. `http://localhost:8000` — phương án cuối cùng
 *
 * Trước khi có resolver này, 3 service trên bỏ qua bước (1) và luôn đi
 * thẳng từ (2)/(3) — tái diễn nguyên văn sự cố "pod API tự gọi chính nó"
 * (đổi URL qua Portal Settings không có tác dụng với các service này).
 *
 * Ghi chú: `SettingsService` và `InternalController` cũng có logic tương tự
 * nhưng nằm ngoài phạm vi refactor này — chuyển chúng sang dùng resolver
 * này để chỉ còn một nơi định nghĩa thứ tự ưu tiên là việc cần làm tiếp theo.
 */
@Injectable()
export class VoiceWorkerUrlResolver {
  constructor(
    @InjectRepository(VoiceWorkerSettings)
    private readonly voiceWorkerRepo: Repository<VoiceWorkerSettings>,
    private readonly config: ConfigService,
  ) {}

  async resolve(): Promise<string> {
    const row = await this.voiceWorkerRepo.findOne({ where: { id: DEFAULT_ID } })
    if (row?.internalUrl) return row.internalUrl
    return this.config.get<string>('VOICE_WORKER_URL', FALLBACK_URL)
  }
}
