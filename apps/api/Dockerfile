# syntax=docker/dockerfile:1
FROM node:20-slim AS base
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/shared/package.json packages/shared/package.json
COPY apps/api/package.json apps/api/package.json
RUN pnpm install --frozen-lockfile

FROM deps AS build
COPY packages/shared packages/shared
COPY apps/api apps/api
RUN pnpm --filter @ai-voice/shared build && pnpm --filter @ai-voice/api build
RUN pnpm deploy --filter @ai-voice/api --prod /out

FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /out/dist ./dist
COPY --from=build /out/node_modules ./node_modules
EXPOSE 3001
CMD ["node", "dist/main"]
