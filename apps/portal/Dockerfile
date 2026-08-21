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
COPY apps/portal/custom-server.js ./apps/portal/custom-server.js
EXPOSE 3000
CMD ["node", "apps/portal/custom-server.js"]
