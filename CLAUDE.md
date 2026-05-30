# DoctorCheck AI Call System

AI Call system thay thế nhân viên chăm sóc khách hàng tổng đài cho phòng khám DoctorCheck.

## Kiến trúc

```
apps/portal/        Next.js 15 App Router — Portal vận hành
apps/api/           NestJS monolith modular — Orchestration API
services/voice/     Python greenfield — Voice worker (STT/TTS/Runtime)
packages/shared/    Zod schemas, types, prosody constants
deploy/k8s/         OrbStack K8s manifests (namespace: ai-voice)
docker-compose.yml  Local dev infra (Postgres, Redis, MinIO)
```

## Stack

- **Portal:** Next.js 15, TypeScript, shadcn/ui, TanStack Query
- **API:** NestJS, TypeScript, PostgreSQL (TypeORM), Redis, JWT/RBAC
- **Voice:** Python 3.12+, FastAPI, faster-whisper (STT), qwen-tts (TTS)
- **Infra:** Kubernetes trên OrbStack, namespace `ai-voice`
- **Portal URL (local K8s):** `http://doctorcheck.ai-agent.local`

## ECC Skills chính

| Skill | Khi nào dùng |
|-------|-------------|
| `backend-patterns` | NestJS modules, DTOs, guards, pipes |
| `frontend-patterns` | Next.js App Router, Server Components, TanStack Query |
| `frontend-design` | Portal UI — design intentional, không dùng default template |
| `python-patterns` | Voice worker services, async patterns |
| `python-testing` | pytest, asyncio, test isolation |
| `postgres-patterns` | Query optimization, schema design |
| `database-migrations` | TypeORM migrations, rollback strategy |
| `docker-patterns` | Docker multi-stage builds |
| `deployment-patterns` | K8s manifests, health probes, resource limits |
| `tdd-workflow` | Viết test trước khi implement |
| `api-design` | REST contract, versioning, error envelope |
| `security-review` | Auth, RBAC, PII masking, audit log |
| `omni-hitl` | HITL learning loop — QA approve trước khi publish |
| `continuous-learning` | Signal extractor → learning proposals |

## Quy tắc dự án

### Bất biến quan trọng

- **Script source of truth:** PostgreSQL qua Script CMS — không dùng file JSON trong repo (trừ `scripts/examples/` làm mẫu)
- **Học qua HITL:** Hệ thống đề xuất, QA duyệt, Admin publish — KHÔNG auto-deploy lên production
- **Audit mọi mutation:** Mọi thay đổi script, publish, settings → `audit_events` table
- **PII masking:** Mask SĐT trong audit log và transcript

### Voice Worker

- Viết mới hoàn toàn tại `services/voice/` — không copy code cũ từ `voice/` (đã xóa)
- Prosody constants từ `packages/shared/constants/prosody.ts` (TypeScript) + Python mirror
- Pause tiers: `none`, `micro`, `short`, `breath`, `medium`, `long`, `turn`
- Streaming-first từ đầu — đo TTFA (Time-To-First-Audio) sớm

### RBAC

| Role | Quyền |
|------|-------|
| `admin` | Users, CloudFone config, publish script |
| `operator` | Campaign on/off, monitor calls |
| `qa` | Review calls, score, approve learning |
| `viewer` | Reports read-only |

### K8s Local Dev

```bash
# Khởi động infra local
docker-compose up -d

# Deploy lên OrbStack K8s
kubectl apply -k deploy/k8s/

# Portal URL
open http://doctorcheck.ai-agent.local
```

### Monorepo commands

```bash
# Root
pnpm install          # cài deps tất cả workspaces
pnpm build            # build tất cả
pnpm typecheck        # type-check tất cả

# Portal
pnpm --filter portal dev
pnpm --filter portal build

# API
pnpm --filter api dev
pnpm --filter api build

# Voice worker
cd services/voice
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```

## Sprint roadmap

| Sprint | Deliverable |
|--------|-------------|
| **S1** | ✅ Cleanup legacy + contract docs + monorepo scaffold + K8s base + auth/RBAC/audit |
| **S2** | ✅ Script CMS — Campaign + ScriptVersion entities, lint L001-L008, CRUD + publish API, Portal scripts pages |
| **S3** | ✅ Python voice worker — SessionState FSM, IntentMatcher, Executor, mock call replay endpoint |
| **S4** | ✅ Call logging + Portal call detail + QA scoring — CallSession, QaScore entities, QA queue |
| **S5** | ✅ CloudFone mock WS + streaming TTS beats — protocol types, beat streamer, TTFA measurement |
| **S6** | ✅ ODS client stub + Dashboard live monitor (ODS schema pending from CloudFone) |
| **S7** | ✅ Analytics dashboard scaffold — Reports page (charts in next iteration) |
| **S8** | ✅ Learning proposals + HITL review queue — LearningProposal entity, approve/reject API |
| **SA** | ✅ Portal auth E2E — /login page, httpOnly cookie, Next.js middleware, serverFetch, seed users (POST /dev/seed), /audit page, route group restructure |
| **SB** | ✅ Script workflow wired — PATCH /scripts/:id (toggle isActive), publishedVersionId FK, VersionActions + CampaignToggle client components |
| **SC** | ✅ Dashboard real KPIs — AnalyticsModule (/analytics/overview, calls-by-day, qa-trends, duration), /health/deps (Postgres + Redis), Call detail with transcript + QA |
| **SD** | ✅ Learning HITL wired — POST /learning/proposals/:id/apply, ProposalActions (approve/reject/apply) client component |
| **SE** | ✅ Reports charts — SVG bar charts for calls-by-day + QA trends + duration table |
| **SF** | ✅ CloudFone test — POST /settings/cloudfone/test, Test kết nối button in settings |
| **SG** | ✅ Schema complete — 9 missing entities added (CallTurn, CallRecording, CallMetrics, LearningApplication, AnalyticsDaily, ServiceApiKey, VoiceProfile, HotlineRoute, RefreshToken), GET /calls/:id/turns+recording, POST /auth/refresh, refresh_token cookie flow |
| **SH** | ✅ Knowledge Base RAG — KnowledgeModule (NestJS CRUD + rag-export), fastembed multilingual-e5-large, in-memory store + cosine search, gender detection F0 pitch analysis, /rag/* endpoints, Portal KB CMS (list/create/edit), sidebar nav |
| **P1** | ✅ Phase 1 Real Call Loop — AudioPipeline wired (async/sync STT), background pipeline_task, barge-in via pipeline VAD, Simulator audio_frame mode |
| **P2** | ✅ Phase 2 RAG in Call — LLM path removed from AiDrivenExecutor, vector RAG in process_utterance (rag_assisted mode), linkedKbTags tag filter in store.search() |
| **P3** | ✅ Phase 3 Expert Handoff — Redis subscriber answer:{sessionId}, question_timeout=60s, Telegram callback_url, half-duplex gate, NestJS forward answer to voice worker |
| **P4** | ✅ Phase 4 Call Persistence — POST /internal/call-events on hangup, dual-write call_turns + CallMetrics (bargeInCount, noMatchCount) |
| **P5** | ✅ Phase 5 Audio Quality — half-duplex suppress (300ms), min_speech_duration_ms=200 (anti-echo), on_tts_start/end in VADDetector |
| **P7** | ✅ Phase 7 Polish — Portal RBAC nav filtering by role, applyProposal merges payload, learning_applications row on apply, signal extractor noMatch→proposals |

## Call Script Contract

- **Spec:** `docs/call-script-contract-v0.1.md`
- **JSON Schema:** `schemas/call-script.v0.1.schema.json`
- **Example:** `scripts/examples/booking_inbound_v1.json`

## Blocker / Rủi ro

- **ODS WS doc:** CloudFone gateway bị block đến khi có schema từ ODS → Phase 4a dùng mock
- **TTS latency:** TTFA target <400ms — đo sớm ở Sprint 3
- **OrbStack GPU:** Confirm MPS passthrough cho TTS pod; fallback CPU
- **Reference voice:** `samples/voice/reference.wav` có thể cần re-record ở 8kHz phone band
