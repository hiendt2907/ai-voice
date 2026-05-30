import { Controller, Get } from '@nestjs/common'
import { InjectDataSource } from '@nestjs/typeorm'
import { DataSource } from 'typeorm'
import Redis from 'ioredis'

let _redis: Redis | null = null
function getRedis(): Redis {
  if (!_redis) {
    _redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379', {
      lazyConnect: true,
      connectTimeout: 2000,
      maxRetriesPerRequest: 0,
    })
  }
  return _redis
}

@Controller('health')
export class HealthController {
  constructor(@InjectDataSource() private readonly ds: DataSource) {}

  @Get()
  check() {
    return { status: 'ok', timestamp: new Date().toISOString() }
  }

  @Get('deps')
  async checkDeps() {
    const [pgOk, redisOk] = await Promise.all([
      this.ds.query('SELECT 1').then(() => true).catch(() => false),
      getRedis().ping().then(() => true).catch(() => false),
    ])
    return {
      postgres: pgOk ? 'ok' : 'error',
      redis: redisOk ? 'ok' : 'error',
      timestamp: new Date().toISOString(),
    }
  }
}
