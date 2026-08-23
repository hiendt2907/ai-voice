import { ExecutionContext, UnauthorizedException } from '@nestjs/common'
import { ConfigService } from '@nestjs/config'
import * as bcrypt from 'bcrypt'
import { InternalAuthGuard } from './internal-auth.guard'
import { ServiceApiKey } from './service-api-key.entity'

function mockContext(headers: Record<string, string>): ExecutionContext {
  return {
    switchToHttp: () => ({
      getRequest: () => ({ headers }),
    }),
  } as unknown as ExecutionContext
}

describe('InternalAuthGuard', () => {
  const repo = { find: jest.fn() }
  const config = { get: jest.fn() }

  const buildGuard = () =>
    new InternalAuthGuard(repo as any, config as unknown as ConfigService)

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('rejects when x-internal-key header is missing', async () => {
    const guard = buildGuard()
    await expect(guard.canActivate(mockContext({}))).rejects.toThrow(UnauthorizedException)
    expect(repo.find).not.toHaveBeenCalled()
  })

  it('accepts a header that bcrypt-matches an active ServiceApiKey row', async () => {
    const plainKey = 'sk-voice-worker-abc123'
    const keyHash = await bcrypt.hash(plainKey, 12)
    repo.find.mockResolvedValue([{ id: '1', isActive: true, keyHash } as ServiceApiKey])

    const guard = buildGuard()
    await expect(
      guard.canActivate(mockContext({ 'x-internal-key': plainKey })),
    ).resolves.toBe(true)
    expect(repo.find).toHaveBeenCalledWith({ where: { isActive: true } })
  })

  it('rejects a header that does not match any active key', async () => {
    const keyHash = await bcrypt.hash('the-real-key', 12)
    repo.find.mockResolvedValue([{ id: '1', isActive: true, keyHash } as ServiceApiKey])

    const guard = buildGuard()
    await expect(
      guard.canActivate(mockContext({ 'x-internal-key': 'wrong-key' })),
    ).rejects.toThrow(UnauthorizedException)
  })

  it('falls back to SERVICE_API_KEY env var when the table is empty', async () => {
    repo.find.mockResolvedValue([])
    config.get.mockImplementation((key: string) => (key === 'SERVICE_API_KEY' ? 'env-secret' : undefined))

    const guard = buildGuard()
    await expect(
      guard.canActivate(mockContext({ 'x-internal-key': 'env-secret' })),
    ).resolves.toBe(true)
  })

  it('rejects a wrong key against the env var fallback', async () => {
    repo.find.mockResolvedValue([])
    config.get.mockImplementation((key: string) => (key === 'SERVICE_API_KEY' ? 'env-secret' : undefined))

    const guard = buildGuard()
    await expect(
      guard.canActivate(mockContext({ 'x-internal-key': 'wrong' })),
    ).rejects.toThrow(UnauthorizedException)
  })

  it('rejects everything when the table is empty AND no env var is configured (fail-closed, not fail-open)', async () => {
    repo.find.mockResolvedValue([])
    config.get.mockReturnValue(undefined)

    const guard = buildGuard()
    await expect(
      guard.canActivate(mockContext({ 'x-internal-key': 'anything' })),
    ).rejects.toThrow(UnauthorizedException)
  })
})
