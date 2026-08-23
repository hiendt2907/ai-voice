---
name: dev-loop
description: "Vòng lặp tự động: build → restart → simulator → debug → plan fix → fix → lặp lại. Tối đa 3 vòng."
origin: local
---

# /dev-loop — Vòng lặp test thực tế + tự sửa

Chạy simulator thực tế, đọc output thật, debug từ logs, fix lỗi thật. Không mô tả — làm.

**Giới hạn:** 3 vòng. Vượt quá → escalate cho user.

---

## Vòng lặp chính

Lặp lại các Phase dưới đây. Sau mỗi vòng in: `=== VÒNG N/3 ===`

---

## Phase 1 — BUILD

```bash
pnpm --filter api build 2>&1 | tail -20
```

```bash
pnpm --filter portal build 2>&1 | tail -10
```

**Quy tắc:**
- `compiled successfully` / `webpack ... compiled` → BUILD PASS
- `compiled with X errors` / `Error` / exit ≠ 0 → BUILD FAIL → nhảy Phase 4 ngay

---

## Phase 2 — RESTART & LOG CHECK

```bash
pm2 restart ai-voice-api ai-voice-portal ai-voice-worker && sleep 5
```

```bash
pm2 logs ai-voice-api --lines 25 --nostream 2>&1 | grep -E "ERROR|error|Traceback|Listening|running"
pm2 logs ai-voice-worker --lines 25 --nostream 2>&1 | grep -E "ERROR|error|Traceback|loaded|started|RAG"
```

**SERVICE FAIL** nếu thấy: `Error:`, `Traceback`, `EADDRINUSE`, `ImportError`, `SyntaxError`
**SERVICE OK** nếu thấy: `Listening`, `Application is running`, `RAG store loaded`

Nếu SERVICE FAIL → ghi nhận lỗi cụ thể, nhảy Phase 4.

---

## Phase 3 — TEST THỰC TẾ

Chỉ chạy khi Phase 1 + 2 đều PASS.

### 3a. Python tests

```bash
cd /Users/hiendang/ai-voice/services/voice && uv run pytest tests/ -v --tb=short 2>&1 | tail -40
```

Ghi nhận: số passed/failed, tên test fail, error message cụ thể.

### 3b. Simulator — test cuộc gọi thực tế

```bash
cd /Users/hiendang/ai-voice && python3 scripts/ws-simulator.py 2>&1
```

**Đọc output simulator:**
- `← Turn N Bot: <text>` → AI đã trả lời, đọc nội dung xem có đúng không
- `Không có audio` → beat-only mode (bình thường nếu use_real_tts=False)
- `WS error` → connection bị drop, xem logs worker ngay sau đó
- Không có Turn 1/2/3 → utterances không được xử lý

**Đọc logs worker ngay sau simulator:**

```bash
pm2 logs ai-voice-worker --lines 40 --nostream 2>&1 | grep -E "RAG|cache|SHADOW|MEDIUM|error|WARNING|utterance|STT"
```

**Phân tích simulator output:**
- RAG hit scores: bình thường 0.6–0.9, dưới 0.65 = fallback
- Cache hit: "RAG cache hit" = text cache hoạt động
- Shadow/Medium log: "[SHADOW]" hoặc "[MEDIUM]" = interception mode hoạt động
- Thời gian: ghi nhận TTFA nếu đo được

### 3c. Health check

```bash
curl -sf http://localhost:3001/api/v1/health && echo " → API OK" || echo " → API FAIL"
curl -sf http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f' → WORKER OK (tts={d.get(\"tts\",\"?\")})')" 2>/dev/null || echo " → WORKER FAIL"
```

---

## Phase 4 — PLAN FIX

Trước khi code, **phân tích nguyên nhân** từ output thực tế:

```
Lỗi: [copy nguyên văn error/output bất thường]
Nguyên nhân: [phán đoán: logic sai / import sai / threshold sai / data thiếu / ...]
File liên quan: [path:line nếu biết]
Fix cần làm: [mô tả ngắn — tối đa 3 bullet]
Rủi ro: [có thể break gì không]
```

Chỉ khi plan rõ ràng → thực hiện fix.

---

## Phase 5 — FIX

Đọc file cụ thể trước khi sửa:

```bash
# Luôn đọc đúng file + dòng từ error trước khi Edit
```

**Nguyên tắc:**
- Fix **đúng chỗ** báo lỗi, không sửa lan rộng
- Python: `dataclasses.replace()` nếu cần copy dataclass
- TypeScript: không dùng `any` để che lỗi type
- Không xóa test để pass — chỉ fix implementation
- Thiếu dependency: `uv add <pkg>` hoặc `pnpm --filter <app> add <pkg>`

Sau khi fix → quay **Phase 1** vòng tiếp theo.

---

## Phase 6 — Quyết định

```
Tất cả Phase 1-3 PASS + simulator output hợp lý?
  └─ Có  → In DONE REPORT, kết thúc
  └─ Không
       └─ Vòng < 3? → in tóm tắt vòng, quay Phase 1
       └─ Vòng = 3? → in ESCALATION REPORT, dừng
```

### DONE REPORT

```
=== DEV-LOOP HOÀN TẤT ✓ (vòng N/3) ===

Build API:        PASS
Build Portal:     PASS
Python tests:     X passed, 0 failed
API health:       UP
Worker health:    UP (tts=elevenlabs|gwen-tts|mock)
Simulator:        N turns, RAG hits [score range], cache [hit/miss]

Files đã sửa:
  - path/to/file.py (lý do ngắn gọn)

→ Sẵn sàng commit.
```

### TÓM TẮT MỖI VÒNG

```
=== VÒNG N/3 — còn lỗi ===
Lỗi gặp:    [copy error thực tế]
Nguyên nhân: [phân tích]
Đã sửa:     [file + thay đổi gì]
Tiếp tục vòng N+1...
```

### ESCALATION REPORT (hết 3 vòng)

```
=== DEV-LOOP ESCALATE (3/3 vòng) ===

Lỗi chưa fix được:
  [copy nguyên văn error]

Simulator output cuối:
  [copy output thực tế]

Đã thử (3 vòng):
  Vòng 1: [sửa gì]
  Vòng 2: [sửa gì]
  Vòng 3: [sửa gì]

Cần user quyết định:
  1. Tiếp tục /dev-loop ?
  2. Xem thủ công: [file cụ thể, dòng N] ?
  3. Bỏ qua tạm?
```

---

## Dừng ngay (không loop)

- Lỗi **external**: DB down, Redis không chạy, `.env` thiếu key thật → báo user
- Lỗi **test logic sai** (test expect sai, không phải code sai) → hỏi user trước khi sửa test
- Lỗi lặp lại **y hệt** qua 2 vòng → escalate ngay, không tiếp tục loop
- ElevenLabs quota error → không phải lỗi code, báo user nạp credit
