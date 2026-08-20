# DoctorCheck AI Call System

AI Call system thay thế nhân viên chăm sóc khách hàng tổng đài cho phòng khám DoctorCheck.

## ⚠️ BẮT BUỘC ĐỌC TRƯỚC MỖI SESSION MỚI

Trước khi làm bất cứ việc gì, đọc theo đúng thứ tự sau. Bỏ qua bước này đã nhiều lần dẫn tới
việc chẩn đoán sai nguyên nhân và "sửa" thứ vốn không hỏng:

1. **Memory** — `~/.claude/projects/-Users-hiendang-ai-voice/memory/MEMORY.md` rồi mở các file
   được index có liên quan tới việc sắp làm. Đây là nơi ghi các lỗi đã tốn nhiều giờ để tìm ra,
   kèm bằng chứng đo được. Rất nhiều "phát hiện mới" thực ra đã nằm sẵn ở đây.
2. **Kiến trúc** — `docs/ai-streaming-voice-architecture-proposal.md` (thiết kế streaming, ngân
   sách độ trễ, các quyết định A1-A9).
3. **Hợp đồng script** — `docs/call-script-contract-v0.1.md` + `schemas/call-script.v0.1.schema.json`
   khi đụng tới script/FSM.
4. **Mục "Luồng xử lý một lượt thoại"** ngay bên dưới trong file này.

Nguyên tắc bắt buộc khi debug: **đọc log của pod thật, không suy đoán.** Output của simulator chỉ
cho thấy AI nói gì, không cho thấy STT nghe được gì và NLU hiểu ra sao.

## Kiến trúc

```
apps/portal/        Next.js 15 App Router — Portal vận hành
apps/api/           NestJS monolith modular — Orchestration API
services/voice/     Python greenfield — Voice worker (STT/TTS/Runtime)
services/voice/sip/ Softphone SIP/RTP thuần Python (chạy trên Mac)
packages/shared/    Zod schemas, types, prosody constants
deploy/k8s/         K8s manifests (namespace: ai-voice, cluster k3s trên GCP)
scripts/seed/       Bộ dữ liệu NLU tiếng Việt + script nạp
```

### Phân chia máy (quan trọng — đừng làm ngược)

```
Macbook                          GCP (k3s, namespace ai-voice)
├─ SIP/RTP softphone             ├─ voice worker (FastAPI)
│  (voip24h CHẶN IP GCP)         ├─ NestJS API + Postgres + Redis
└─ inference server :8100        └─ Portal
   └─ faster-whisper (STT)
                                 Cloud: xKiro
                                 ├─ TTS  /v1/audio/speech
                                 └─ LLM  /v1/chat/completions
```

- **Mac chỉ chạy SIP + STT.** SIP phải ở Mac vì voip24h chặn IP GCP. STT ở Mac vì **xKiro không
  có endpoint speech-to-text** (`/v1/audio/transcriptions` → 404).
- **Mọi thứ còn lại chạy trên GCP.** Không chạy voice worker local để test trừ khi đang debug
  nhanh — cấu hình DB thắng ConfigMap nên môi trường local dễ khác production.

## Stack

- **Portal:** Next.js 15, TypeScript, shadcn/ui, TanStack Query
- **API:** NestJS, TypeScript, PostgreSQL (TypeORM), Redis, JWT/RBAC
- **Voice:** Python 3.12+, FastAPI, faster-whisper (STT), xKiro (TTS + LLM)
- **Telephony:** voip24h SIP trunk ⇄ `services/voice/sip/` ⇄ giao thức CloudFone qua WS
- **Infra:** k3s trên GCP (`omni-k3s-vm`, asia-southeast1-c), namespace `ai-voice`

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

## Luồng xử lý một lượt thoại

```
Điện thoại ⇄ voip24h ⇄ RTP μ-law 8kHz ⇄ sip/client.py + sip/rtp_session.py   [Mac]
                                         └─ sip/cloudfone_bridge.py (WS, giao thức CloudFone)
                                                              ↓
  ┌───────────────────────────────────────────────────────────────────────┐   [GCP]
  │ audio_frame → VAD → STT (remote → Mac)  ~1000ms                       │
  │        ↓                                                              │
  │ TẦNG 1 — Vector NLU (embedding local, vài ms)                         │
  │   tier=confident → FSM chuyển bước theo script (runtime/executor.py)   │
  │        ↓ không đủ tự tin                                              │
  │ TẦNG 2 — LLM NLU (llm_resolver, ~2000ms) — chỉ khi USE_LLM_NLU=true    │
  │        ↓ vẫn không khớp intent nào                                    │
  │ TẦNG 3 — RAG: tra KB (rag/store.py) → trả lời từ bài viết đã duyệt     │
  │        ↓ RAG không đạt ngưỡng                                         │
  │ TẦNG 4 — LLM reasoning có kiểm soát (call/dialogue.py)                │
  │        ↓ không đủ căn cứ / thuộc chủ đề cấm                           │
  │ TẦNG 5 — Escalate cho người thật (Telegram / handoff)                 │
  │        ↓                                                              │
  │ TTS xKiro (streaming, ~450ms) → audio_chunk → RTP → khách nghe        │
  └───────────────────────────────────────────────────────────────────────┘
```

**Mục tiêu xuyên suốt: đẩy việc xuống tầng thấp nhất có thể.** Tầng 1 gần như miễn phí, tầng 2 tốn
~2 giây. Khi thấy LLM bị gọi nhiều, đó là dấu hiệu **bộ NLU thiếu mẫu**, không phải lý do để tăng
timeout.

### Guardrail của Tầng 4 — 3 lớp, chỉ lớp 3 chạm tới LLM

1. **Blacklist cứng** (`runtime/guardrails.py`) — regex chặn chẩn đoán bệnh, kê đơn/liều lượng,
   tiên lượng, giá chưa duyệt. Chạy **trước** mọi lệnh gọi LLM nên prompt injection từ phía khách
   ("bỏ qua hướng dẫn trước…") không vượt qua được. Quy tắc chỉ nằm trong system prompt thì có thể
   bị nói khéo cho bỏ qua, regex thì không.
2. **Ngưỡng liên quan RAG** (`rag_context_floor`, mặc định 0.45) — không có bài KB nào đủ liên quan
   thì **không gọi LLM**, vì không có gì để ground → đó chính là điều kiện sinh ra bịa đặt.
3. **Model tự từ chối** — system prompt buộc trả về đúng một câu cố định (`REFUSAL_SENTINEL`) khi
   không đủ căn cứ; phát hiện bằng so khớp đầu câu trên luồng streaming rồi escalate thật.

**Bất biến: AI không bao giờ được bịa.** Mọi câu trả lời phải bắt nguồn từ KB đã duyệt hoặc từ
kịch bản. Không có căn cứ → chuyển người thật, không đoán.

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

### Deploy lên GCP

Jenkins (`ai-voice-build`) có tồn tại nhưng **không tự trigger được** (bật xác thực, API token chỉ
lưu hash). Đường deploy thực tế đang dùng:

```bash
SHA=$(git rev-parse --short=7 HEAD)      # commit TRƯỚC rồi mới build, nếu không tag sẽ sai nội dung
docker buildx build --platform linux/amd64 --load \
  -f services/voice/Dockerfile -t harbor.harbor.svc.cluster.local/ai-voice/voice:$SHA services/voice/
docker save harbor.harbor.svc.cluster.local/ai-voice/voice:$SHA -o /tmp/voice-$SHA.tar
shasum -a 256 /tmp/voice-$SHA.tar                       # so khớp với đầu bên kia
gcloud compute scp /tmp/voice-$SHA.tar omni-k3s-vm:/tmp/ --zone=asia-southeast1-c
gcloud compute ssh omni-k3s-vm --zone=asia-southeast1-c \
  --command="sudo k3s ctr -n k8s.io images import /tmp/voice-$SHA.tar"
kubectl set image deployment/voice voice=harbor.harbor.svc.cluster.local/ai-voice/voice:$SHA -n ai-voice
```

**Docker trên Mac chính là OrbStack** — tắt OrbStack là mất khả năng build.

**Sau mỗi lần pod đổi, `kubectl port-forward` chết im lặng** (`failed to find sandbox`), phía
softphone báo `ConnectionRefusedError [Errno 61]`. Phải khởi động lại port-forward.

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

## Test thực tế 1 cuộc gọi (bắt buộc trước khi báo cáo phase)

Test coverage bằng pytest (mock-based) KHÔNG đủ để coi một phase là "xong" — bắt buộc phải chạy
thử một cuộc gọi thật qua `simulator/run_sim.py` đấu thẳng vào voice worker đang chạy, trước khi
báo cáo hoàn thành bất kỳ phase/sprint nào liên quan đến `services/voice/`. Đây là bài test mặc
định, không phải tùy chọn.

### Bước 1 (luôn chạy trước) — test audio thật, KHÔNG cần gọi điện

Đây là bài debug/A-B mặc định. Nó đi qua đúng đường của cuộc gọi thật (VAD → STT → NLU → LLM →
TTS), chỉ bỏ tầng SIP/RTP, nên lặp lại được và rẻ.

```bash
# Sinh giọng khách bằng xKiro TTS, 8kHz, CÓ khoảng lặng ≥1.5s giữa các câu.
# Khoảng lặng là phần quan trọng nhất: chính nó phơi ra lỗi Whisper bịa câu lúc im lặng.
# (xem memory wav-pipeline-test-without-calling để lấy đoạn sinh file)

kubectl port-forward -n ai-voice svc/voice 18000:8000 &
cd services/voice
uv run python -m simulator.run_sim --url ws://127.0.0.1:18000/ws/call \
    --script booking_inbound_v1 --wav /tmp/caller_speech.wav

# BẮT BUỘC đọc log pod — simulator KHÔNG hiện STT nghe gì và NLU hiểu ra sao:
kubectl logs -n ai-voice <pod> --tail=60 | grep -E "STT transcript|Vector NLU|LLM NLU|Barge"
```

Test bằng `--utterances` (text giả) **bỏ qua hoàn toàn STT/VAD** — dùng để kiểm tra định tuyến
intent thì được, nhưng không bao giờ đủ để kết luận "cuộc gọi hoạt động".

### Bước 2 — cuộc gọi thật qua voip24h

```bash
cd services/voice
uv run python -m sip.run_softphone \
    --sip-server 222.255.115.80 --sip-user 642 --sip-password '<pass>' \
    --ws-url ws://127.0.0.1:18000/ws/call \
    --script /Users/hiendang/ai-voice/scripts/examples/booking_inbound_v1.json

# Terminal khác — quay số ra:
AUTH=$(python3 -c "import json;print(json.load(open('/tmp/voip24h_auth.json'))['data']['token'])")
curl -s -X POST https://api.voip24h.vn/v3/call/dial \
    -H "Authorization: Bearer $AUTH" -d "extension=642" -d "phone=<số>"
```

voip24h trial giới hạn cứng **~31 giây/cuộc gọi** — không phải bug.

Tiêu chí đạt (đọc trực tiếp từ output simulator):
- Cuộc gọi đi hết turn mà KHÔNG timeout/crash, kết thúc bằng terminal event đúng (booking xong /
  handoff / reprompt tùy kịch bản) — không rơi vào fallback "xin lỗi, hệ thống gặp sự cố" ngoài ý muốn.
- TTFA (Time-To-First-Audio) hiển thị trong output không vượt ngưỡng `--ttfa-warn` (mặc định 500ms,
  target thật là <400ms theo mục Blocker/Rủi ro bên dưới) — giá trị in màu đỏ nghĩa là fail.
- Transcript STT khớp nghĩa với câu thoại đã gửi vào (không lệch nghiêm trọng do model STT).
- Nếu thay đổi động chạm `call/`, `stt/`, `tts/`, hoặc `runtime/`: chạy thêm
  `uv run pytest tests/test_golden_transcripts.py` để xác nhận không có regression so với 5 baseline
  đã capture (`tests/golden/*.json`).

Chỉ sau khi cả 2 lớp test (pytest suite đầy đủ + ít nhất 1 cuộc gọi simulator thật như trên) đều
pass mới được coi phase đó là hoàn thành và báo cáo lại cho user.

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

| **P8** | ✅ Telephony thật — softphone SIP/RTP tự viết (`sip/`) thay FreeSWITCH, bridge sang giao thức CloudFone; chuyển TTS+LLM sang xKiro, Mac chỉ còn SIP+STT |
| **P9** | ✅ NLU/KB chuẩn hoá — bộ 242 mẫu tiếng Việt phủ đủ 13 intent script, vector NLU chạy trước LLM, gỡ whitelist `linkedKbTags`; câu hỏi ngoài kịch bản 2/6 → 6/6, LLM 0 lượt |

## Blocker / Rủi ro

- **ODS WS doc:** CloudFone gateway bị block đến khi có schema từ ODS → Phase 4a dùng mock
- **TTS latency:** target <400ms. Đo thật từ pod GCP: xKiro **~400-550ms, phẳng theo độ dài câu**.
  Che bằng filler ngắn (câu 3 ký tự chỉ 267-304ms) nên cảm nhận vẫn ổn.
- **LLM latency:** xKiro `qwen/qwen3.5-flash` **1835-2318ms/lượt** — quá chậm cho hội thoại. Đây là
  lý do vector NLU phải chạy trước. Khi benchmark: request **giống hệt nhau bị cache trả về 13ms**,
  luôn đổi nội dung mỗi lần đo.
- **STT tiếng Việt:** faster-whisper `small` vẫn sai dấu ở từ chuyên ngành (`nội soi` → `đội soi`).
  Đã mồi `initial_prompt` từ vựng phòng khám; vector NLU chịu được sai lệch này. Nâng lên `medium`
  nếu cần chính xác hơn.
- **`USE_STREAMING_STT` phải để `false`** — bật lên thì Whisper bịa câu YouTube lúc im lặng với
  confidence cao (0.73), gây barge-in giả và phá NLU. Xem memory `streaming-stt-canary-enabled`.
- **voip24h:** chặn IP GCP (SIP chỉ chạy được từ Mac); trial giới hạn ~31 giây/cuộc gọi.
