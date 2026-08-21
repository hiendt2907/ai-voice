import { Injectable, BadRequestException, InternalServerErrorException } from '@nestjs/common'
import { ConfigService } from '@nestjs/config'

export interface DialResult {
  ok: boolean
  message: string
}

interface TokenResponse {
  data?: {
    response?: {
      data?: {
        IsToken?: string
        Expried?: string
      }
    }
  }
}

@Injectable()
export class Voip24hService {
  private readonly apiKey: string
  private readonly apiSecret: string
  private readonly extension: string
  private cachedToken: string | null = null
  private cachedTokenExpiresAt = 0

  constructor(private readonly config: ConfigService) {
    this.apiKey = this.config.get<string>('VOIP24H_API_KEY', '')
    this.apiSecret = this.config.get<string>('VOIP24H_API_SECRET', '')
    this.extension = this.config.get<string>('VOIP24H_EXTENSION', '')
  }

  private async getToken(): Promise<string> {
    // 5-minute safety margin before the real expiry.
    if (this.cachedToken && Date.now() < this.cachedTokenExpiresAt - 5 * 60 * 1000) {
      return this.cachedToken
    }
    if (!this.apiKey || !this.apiSecret) {
      throw new BadRequestException('voip24h chưa được cấu hình (thiếu VOIP24H_API_KEY/VOIP24H_API_SECRET)')
    }

    let res: Response
    try {
      res = await fetch('http://auth2.voip24h.vn/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: this.apiKey, api_secert: this.apiSecret }),
        signal: AbortSignal.timeout(10000),
      })
    } catch (err) {
      throw new InternalServerErrorException(
        `Không lấy được token voip24h: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
    const body = (await res.json().catch(() => ({}))) as TokenResponse
    const token = body.data?.response?.data?.IsToken
    if (!res.ok || !token) {
      throw new InternalServerErrorException('voip24h trả về token rỗng — kiểm tra lại api_key/api_secret')
    }
    this.cachedToken = token
    // Tokens observed with a 24h lifetime; re-derive precisely if the API
    // ever returns a shorter one, but default to 24h minus the margin above.
    const expiredStr = body.data?.response?.data?.Expried
    this.cachedTokenExpiresAt = expiredStr ? new Date(expiredStr.replace(' ', 'T')).getTime() : Date.now() + 24 * 60 * 60 * 1000
    return token
  }

  async dial(phone: string): Promise<DialResult> {
    if (!this.extension) {
      throw new BadRequestException('voip24h chưa được cấu hình (thiếu VOIP24H_EXTENSION)')
    }
    const token = await this.getToken()

    const params = new URLSearchParams({ extension: this.extension, phone })
    let res: Response
    try {
      res = await fetch('https://api.voip24h.vn/v3/call/dial', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: params.toString(),
        signal: AbortSignal.timeout(10000),
      })
    } catch (err) {
      throw new InternalServerErrorException(
        `Không gọi được voip24h: ${err instanceof Error ? err.message : String(err)}`,
      )
    }

    const data = (await res.json().catch(() => ({}))) as { message?: string }
    if (!res.ok) {
      throw new InternalServerErrorException(data.message ?? `voip24h trả lỗi HTTP ${res.status}`)
    }
    return { ok: true, message: data.message ?? 'Đang gọi' }
  }
}
