import { Injectable, UnauthorizedException } from '@nestjs/common'
import { JwtService } from '@nestjs/jwt'
import { ConfigService } from '@nestjs/config'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { randomUUID } from 'crypto'
import { UsersService } from '../users/users.service'
import { User } from '../users/user.entity'
import { RefreshToken } from './refresh-token.entity'

const REFRESH_TTL_DAYS = 7

@Injectable()
export class AuthService {
  constructor(
    private readonly usersService: UsersService,
    private readonly jwtService: JwtService,
    private readonly config: ConfigService,
    @InjectRepository(RefreshToken)
    private readonly refreshRepo: Repository<RefreshToken>,
  ) {}

  async validateUser(email: string, password: string): Promise<User> {
    const user = await this.usersService.findByEmail(email)
    if (!user) throw new UnauthorizedException('Invalid credentials')
    const valid = await this.usersService.verifyPassword(user, password)
    if (!valid) throw new UnauthorizedException('Invalid credentials')
    return user
  }

  async login(user: User) {
    const payload = { sub: user.id, email: user.email, role: user.role }
    const jti = randomUUID()
    const expiresAt = new Date(Date.now() + REFRESH_TTL_DAYS * 86400 * 1000)
    await this.refreshRepo.save(this.refreshRepo.create({ userId: user.id, jti, expiresAt, revokedAt: null }))
    return {
      accessToken: this.jwtService.sign(payload),
      refreshToken: this.jwtService.sign(
        { sub: user.id, jti },
        { secret: this.config.getOrThrow<string>('JWT_REFRESH_SECRET'), expiresIn: `${REFRESH_TTL_DAYS}d` },
      ),
      user: { id: user.id, email: user.email, fullName: user.fullName, role: user.role },
    }
  }

  async refresh(refreshToken: string): Promise<{ accessToken: string }> {
    let payload: { sub: string; jti: string }
    try {
      payload = this.jwtService.verify<{ sub: string; jti: string }>(refreshToken, {
        secret: this.config.getOrThrow<string>('JWT_REFRESH_SECRET'),
      })
    } catch {
      throw new UnauthorizedException('Invalid refresh token')
    }

    const record = await this.refreshRepo.findOne({ where: { jti: payload.jti } })
    if (!record || record.revokedAt || record.expiresAt < new Date()) {
      throw new UnauthorizedException('Refresh token expired or revoked')
    }

    const user = await this.usersService.findById(payload.sub)
    if (!user) throw new UnauthorizedException('User not found')

    const accessToken = this.jwtService.sign({ sub: user.id, email: user.email, role: user.role })
    return { accessToken }
  }
}
