import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['doctorcheck.ai-agent.local', '*.ngrok-free.app', '*.ngrok.app', '*.ngrok.io'],
  transpilePackages: ['@ai-voice/shared'],
  async rewrites() {
    // Only forward the versioned backend namespace. The portal's own route
    // handlers live under non-versioned /api/* (e.g. /api/knowledge/[id]) and
    // add cookie auth — a broad /api/:path* rewrite would shadow the dynamic
    // ones (afterFiles rewrites run before dynamic routes) and send them to the
    // backend, which 404s because it only serves /api/v1/*.
    return [
      {
        source: '/api/v1/:path*',
        destination: `${process.env.API_INTERNAL_URL ?? 'http://localhost:3001'}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
