import * as path from 'path'
import * as dotenv from 'dotenv'
import { DataSource } from 'typeorm'

// Mirror the envFilePath list used by ConfigModule in app.module.ts.
// Later files must not override values already loaded (dotenv default behaviour).
const ENV_FILES = [
  path.resolve(process.cwd(), '.env'),
  path.resolve(process.cwd(), '../../.env'),
  path.resolve(__dirname, '../../../.env'),
]

for (const envFile of ENV_FILES) {
  dotenv.config({ path: envFile })
}

const databaseUrl = process.env.DATABASE_URL

if (!databaseUrl) {
  throw new Error('DATABASE_URL is not configured — required by the TypeORM CLI DataSource')
}

/**
 * DataSource used exclusively by the TypeORM CLI (migration:generate / run / revert).
 *
 * Runtime connection config lives in `app.module.ts` (TypeOrmModule.forRootAsync) and
 * loads migrations from `dist/migrations/*.js`. This CLI DataSource points at the
 * TypeScript sources instead, so generated migrations land in `src/migrations/`.
 */
export const AppDataSource = new DataSource({
  type: 'postgres',
  url: databaseUrl,
  entities: [path.join(__dirname, '/**/*.entity{.ts,.js}')],
  migrations: [path.join(__dirname, '/migrations/*{.ts,.js}')],
  synchronize: false,
  migrationsRun: false,
})
