# syntax=docker/dockerfile:1
FROM node:20-slim AS base
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/shared/package.json packages/shared/package.json
COPY apps/portal/package.json apps/portal/package.json
RUN pnpm install --frozen-lockfile

FROM deps AS build
COPY packages/shared packages/shared
COPY apps/portal apps/portal
RUN pnpm --filter @ai-voice/shared build
RUN pnpm --filter @ai-voice/portal build

FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
COPY --from=build /repo/apps/portal/.next/standalone ./
COPY --from=build /repo/apps/portal/.next/static ./apps/portal/.next/static
COPY apps/portal/ws-proxy.js ./apps/portal/ws-proxy.js
EXPOSE 3000 3001
# Two processes: Next's own generated server.js (unchanged) on :3000, and a
# plain-Node WS proxy for /ws/call on :3001 — see ws-proxy.js docstring for
# why it isn't wired into Next's server directly. `wait -n` exits (and lets
# k8s restart the container) if either process dies.
CMD ["bash", "-c", "node apps/portal/server.js & node apps/portal/ws-proxy.js & wait -n"]
