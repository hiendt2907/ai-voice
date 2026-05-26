import * as path from 'path'
import { Module } from '@nestjs/common'
import { ConfigModule, ConfigService } from '@nestjs/config'
import { TypeOrmModule } from '@nestjs/typeorm'
import { AuthModule } from './auth/auth.module'
import { UsersModule } from './users/users.module'
import { AuditModule } from './audit/audit.module'
import { HealthModule } from './health/health.module'
import { ScriptsModule } from './scripts/scripts.module'
import { CallsModule } from './calls/calls.module'
import { InternalModule } from './internal/internal.module'
import { LearningModule } from './learning/learning.module'
import { SettingsModule } from './settings/settings.module'

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: [
        path.resolve(process.cwd(), '.env'),
        path.resolve(process.cwd(), '../../.env'),
        path.resolve(__dirname, '../../../.env'),
      ],
    }),
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'postgres',
        url: config.getOrThrow<string>('DATABASE_URL'),
        autoLoadEntities: true,
        synchronize: process.env.NODE_ENV !== 'production',
        migrations: ['dist/migrations/*.js'],
        migrationsRun: process.env.NODE_ENV === 'production',
      }),
    }),
    AuthModule,
    UsersModule,
    AuditModule,
    HealthModule,
    ScriptsModule,
    CallsModule,
    InternalModule,
    LearningModule,
    SettingsModule,
  ],
})
export class AppModule {}
