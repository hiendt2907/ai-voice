const path = require('path')
const root = __dirname
const envFile = path.join(root, '.env')

module.exports = {
  apps: [
    {
      name: 'ai-voice-api',
      cwd: path.join(root, 'apps/api'),
      script: 'pnpm',
      args: 'dev',
      env_file: envFile,
      watch: false,
      autorestart: true,
      max_restarts: 5,
    },
    {
      name: 'ai-voice-portal',
      cwd: path.join(root, 'apps/portal'),
      script: 'pnpm',
      args: 'dev',
      env_file: envFile,
      watch: false,
      autorestart: true,
      max_restarts: 5,
    },
    {
      name: 'ai-voice-worker',
      cwd: path.join(root, 'services/voice'),
      script: 'uv',
      args: 'run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload',
      env_file: envFile,
      watch: false,
      autorestart: true,
      max_restarts: 5,
      interpreter: 'none',
    },
  ],
}
