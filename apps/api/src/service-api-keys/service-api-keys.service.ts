import { Injectable, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { randomBytes } from 'crypto'
import * as bcrypt from 'bcrypt'
import { ServiceApiKey } from '../internal/service-api-key.entity'

export interface CreatedKeyResult {
  id: string
  name: string
  isActive: boolean
  createdAt: Date
  /** Giá trị plaintext — CHỈ trả về đúng một lần lúc tạo, không lưu lại ở đâu. */
  plaintextKey: string
}

// 32 byte hex = 64 ký tự, cùng độ dài với SERVICE_API_KEY bootstrap hiện có
// trong Vault — không phải yêu cầu bắt buộc của guard (guard chỉ so bcrypt/
// so chuỗi thô, không quan tâm độ dài), nhưng giữ nhất quán cho dễ vận hành.
const KEY_BYTES = 32
const BCRYPT_SALT_ROUNDS = 12 // khớp users.service.ts — cùng convention hash trong repo

@Injectable()
export class ServiceApiKeysService {
  constructor(
    @InjectRepository(ServiceApiKey)
    private readonly repo: Repository<ServiceApiKey>,
  ) {}

  /** Không bao giờ trả keyHash ra ngoài — danh sách chỉ có id/name/isActive/createdAt. */
  async list(): Promise<Omit<ServiceApiKey, 'keyHash'>[]> {
    const rows = await this.repo.find({ order: { createdAt: 'DESC' } })
    return rows.map(({ keyHash: _keyHash, ...rest }) => rest)
  }

  async create(name: string): Promise<CreatedKeyResult> {
    const plaintextKey = randomBytes(KEY_BYTES).toString('hex')
    const keyHash = await bcrypt.hash(plaintextKey, BCRYPT_SALT_ROUNDS)
    const saved = await this.repo.save(this.repo.create({ name, keyHash, isActive: true }))
    return {
      id: saved.id,
      name: saved.name,
      isActive: saved.isActive,
      createdAt: saved.createdAt,
      plaintextKey,
    }
  }

  /**
   * Thu hồi (soft-delete) — KHÔNG xoá hàng, để giữ lịch sử/audit trail.
   * Guard chỉ nạp key có isActive=true nên hàng bị thu hồi lập tức mất hiệu lực.
   */
  async revoke(id: string): Promise<Omit<ServiceApiKey, 'keyHash'>> {
    const row = await this.repo.findOne({ where: { id } })
    if (!row) throw new NotFoundException(`ServiceApiKey ${id} not found`)
    row.isActive = false
    const saved = await this.repo.save(row)
    const { keyHash: _keyHash, ...rest } = saved
    return rest
  }
}
