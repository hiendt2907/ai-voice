import * as bcrypt from 'bcrypt'
import { NotFoundException } from '@nestjs/common'
import { ServiceApiKeysService } from './service-api-keys.service'

describe('ServiceApiKeysService', () => {
  const repo = {
    find: jest.fn(),
    create: jest.fn((v: unknown) => v),
    save: jest.fn(),
    findOne: jest.fn(),
  }

  const buildService = () => new ServiceApiKeysService(repo as any)

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('list', () => {
    it('never returns keyHash', async () => {
      repo.find.mockResolvedValue([
        { id: '1', name: 'a', isActive: true, createdAt: new Date(), keyHash: 'secret-hash' },
      ])
      const svc = buildService()

      const result = await svc.list()

      expect(result[0]).not.toHaveProperty('keyHash')
      expect(result[0]).toEqual({ id: '1', name: 'a', isActive: true, createdAt: expect.any(Date) })
    })
  })

  describe('create', () => {
    it('returns a plaintext key whose bcrypt hash matches the stored keyHash', async () => {
      let savedRow: any
      repo.save.mockImplementation((row: any) => {
        savedRow = { ...row, id: 'new-id', createdAt: new Date() }
        return savedRow
      })
      const svc = buildService()

      const created = await svc.create('voice-worker-prod')

      expect(created.name).toBe('voice-worker-prod')
      expect(created.isActive).toBe(true)
      expect(created.plaintextKey).toHaveLength(64) // 32 bytes hex
      const matches = await bcrypt.compare(created.plaintextKey, savedRow.keyHash)
      expect(matches).toBe(true)
    })

    it('generates a different key on each call (no reuse)', async () => {
      repo.save.mockImplementation((row: any) => ({ ...row, id: 'x', createdAt: new Date() }))
      const svc = buildService()

      const a = await svc.create('key-a')
      const b = await svc.create('key-b')

      expect(a.plaintextKey).not.toBe(b.plaintextKey)
    })
  })

  describe('revoke', () => {
    it('sets isActive to false and strips keyHash from the result', async () => {
      repo.findOne.mockResolvedValue({ id: '1', name: 'a', isActive: true, keyHash: 'h', createdAt: new Date() })
      repo.save.mockImplementation((row: any) => row)
      const svc = buildService()

      const result = await svc.revoke('1')

      expect(result.isActive).toBe(false)
      expect(result).not.toHaveProperty('keyHash')
    })

    it('throws NotFoundException for an unknown id', async () => {
      repo.findOne.mockResolvedValue(null)
      const svc = buildService()

      await expect(svc.revoke('missing')).rejects.toThrow(NotFoundException)
    })
  })
})
