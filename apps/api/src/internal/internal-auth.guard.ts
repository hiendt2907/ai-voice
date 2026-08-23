import {
  Injectable,
  CanActivate,
  ExecutionContext,
  UnauthorizedException,
  Logger,
} from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { ConfigService } from '@nestjs/config'
import * as bcrypt from 'bcrypt'
import { createHash, timingSafeEqual } from 'crypto'
import { ServiceApiKey } from './service-api-key.entity'

const INTERNAL_KEY_HEADER = 'x-internal-key'

/**
 * Chặn truy cập /internal/* — các endpoint service-to-service (voice worker ⇄
 * NestJS) trước đây KHÔNG có @UseGuards nào, cộng với ingress route "/" không
 * loại trừ /internal nên toàn bộ payload nội bộ (system-settings gồm mật khẩu
 * SIP dạng thật, NLU/KB export, ghi call-events) từng lộ ra internet không cần
 * token. Đây là lớp phòng thủ ở tầng ứng dụng, độc lập với lớp ingress
 * (deploy/k8s/api/ingress.yaml) — hỏng một lớp thì lớp kia vẫn chặn.
 *
 * Cơ chế xác thực: header `x-internal-key` phải khớp keyHash (bcrypt, cùng
 * cách repo hash mật khẩu user ở users.service.ts) của MỘT bản ghi
 * ServiceApiKey đang isActive=true.
 *
 * Fallback khi bảng service_api_keys RỖNG (đúng thực trạng production hiện
 * tại): so khớp với biến môi trường SERVICE_API_KEY / INTERNAL_API_KEY —
 * đúng 2 field voice worker (`services/voice/api/config.py`) đã có sẵn để
 * gửi header này. Lý do chọn fallback thay vì "bảng rỗng thì cho qua": nếu
 * cho qua khi rỗng, lỗ hổng coi như KHÔNG được vá (mặc định production hôm
 * nay chính là bảng rỗng). Fallback so khớp bằng digest SHA-256 +
 * timingSafeEqual để không lộ thông tin qua độ dài chuỗi hay thời gian so
 * sánh sớm dừng.
 *
 * HỆ QUẢ VẬN HÀNH: nếu KHÔNG tạo ServiceApiKey và KHÔNG set biến môi trường
 * nói trên, guard sẽ từ chối luôn (tình huống tự khoá chính mình). Người vận
 * hành bắt buộc phải làm một trong hai việc sau khi deploy bản vá này, xem
 * chi tiết trong báo cáo cuối của agent đã tạo guard này.
 */
@Injectable()
export class InternalAuthGuard implements CanActivate {
  private readonly logger = new Logger(InternalAuthGuard.name)
  private hasWarnedFallback = false

  constructor(
    @InjectRepository(ServiceApiKey)
    private readonly serviceApiKeyRepo: Repository<ServiceApiKey>,
    private readonly config: ConfigService,
  ) {}

  async canActivate(ctx: ExecutionContext): Promise<boolean> {
    const request = ctx
      .switchToHttp()
      .getRequest<{ headers: Record<string, string | string[] | undefined> }>()
    const providedKey = request.headers[INTERNAL_KEY_HEADER]

    if (typeof providedKey !== 'string' || providedKey.length === 0) {
      throw new UnauthorizedException('Unauthorized')
    }

    const activeKeys = await this.serviceApiKeyRepo.find({ where: { isActive: true } })

    if (activeKeys.length > 0) {
      const matches = await Promise.all(
        activeKeys.map((key) => bcrypt.compare(providedKey, key.keyHash)),
      )
      if (matches.some(Boolean)) {
        return true
      }
      throw new UnauthorizedException('Unauthorized')
    }

    // Không có key nào trong DB — fallback về biến môi trường bootstrap.
    const envSecret =
      this.config.get<string>('SERVICE_API_KEY') || this.config.get<string>('INTERNAL_API_KEY')

    if (envSecret) {
      if (!this.hasWarnedFallback) {
        this.hasWarnedFallback = true
        this.logger.warn(
          'Bảng service_api_keys đang rỗng — /internal/* đang xác thực bằng biến môi trường ' +
            'SERVICE_API_KEY/INTERNAL_API_KEY (fallback bootstrap). Hãy tạo ServiceApiKey trong DB ' +
            'và xoay vòng sang cơ chế theo hàng khi có thể.',
        )
      }
      if (this.constantTimeEquals(providedKey, envSecret)) {
        return true
      }
      throw new UnauthorizedException('Unauthorized')
    }

    // Bảng rỗng VÀ không có biến môi trường nào được cấu hình — từ chối hết,
    // KHÔNG cho qua. Đây là lựa chọn có chủ đích: bảng rỗng không được phép
    // đồng nghĩa với "mở cửa", nếu không lỗ hổng coi như chưa vá.
    this.logger.warn(
      'Từ chối request /internal/* — bảng service_api_keys rỗng và không có ' +
        'SERVICE_API_KEY/INTERNAL_API_KEY trong môi trường. Cấu hình một trong hai để voice ' +
        'worker gọi lại được.',
    )
    throw new UnauthorizedException('Unauthorized')
  }

  /** So khớp không lộ độ dài/thời gian: hash SHA-256 cả hai vế về cùng độ dài cố định rồi so. */
  private constantTimeEquals(a: string, b: string): boolean {
    const digestA = createHash('sha256').update(a).digest()
    const digestB = createHash('sha256').update(b).digest()
    return timingSafeEqual(digestA, digestB)
  }
}
