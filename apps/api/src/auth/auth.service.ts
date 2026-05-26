import { Injectable, UnauthorizedException } from '@nestjs/common'
import { JwtService } from '@nestjs/jwt'
import { UsersService } from '../users/users.service'
import { User } from '../users/user.entity'

@Injectable()
export class AuthService {
  constructor(
    private readonly usersService: UsersService,
    private readonly jwtService: JwtService,
  ) {}

  async validateUser(email: string, password: string): Promise<User> {
    const user = await this.usersService.findByEmail(email)
    if (!user) throw new UnauthorizedException('Invalid credentials')
    const valid = await this.usersService.verifyPassword(user, password)
    if (!valid) throw new UnauthorizedException('Invalid credentials')
    return user
  }

  login(user: User) {
    const payload = { sub: user.id, email: user.email, role: user.role }
    return {
      accessToken: this.jwtService.sign(payload),
      user: { id: user.id, email: user.email, fullName: user.fullName, role: user.role },
    }
  }
}
