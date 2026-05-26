import { Injectable, NotFoundException, ConflictException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import * as bcrypt from 'bcrypt'
import { User } from './user.entity'
import { Role } from '@ai-voice/shared'

@Injectable()
export class UsersService {
  constructor(@InjectRepository(User) private readonly repo: Repository<User>) {}

  async findByEmail(email: string): Promise<User | null> {
    return this.repo.findOne({ where: { email, isActive: true } })
  }

  async findById(id: string): Promise<User> {
    const user = await this.repo.findOne({ where: { id } })
    if (!user) throw new NotFoundException(`User ${id} not found`)
    return user
  }

  async findAll(): Promise<Omit<User, 'passwordHash'>[]> {
    const users = await this.repo.find({ order: { createdAt: 'DESC' } })
    return users.map(({ passwordHash: _, ...rest }) => rest)
  }

  async create(data: { email: string; password: string; fullName: string; role: Role }): Promise<User> {
    const existing = await this.repo.findOne({ where: { email: data.email } })
    if (existing) throw new ConflictException(`Email ${data.email} already registered`)

    const passwordHash = await bcrypt.hash(data.password, 12)
    const user = this.repo.create({ ...data, passwordHash })
    return this.repo.save(user)
  }

  async verifyPassword(user: User, password: string): Promise<boolean> {
    return bcrypt.compare(password, user.passwordHash)
  }
}
