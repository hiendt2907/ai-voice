---
name: dev-loop
description: "Vòng lặp tự động: reload → check logs → test thực tế → fix → lặp lại cho đến khi xanh. Tối đa 5 vòng."
origin: local
---

# /dev-loop — Vòng lặp tự sửa đến khi xanh

Chạy thực tế từng bước, đọc output thật, fix lỗi thật. Không mô tả — làm.

**Giới hạn:** 5 vòng. Vượt quá → escalate cho user.

---

## Vòng lặp chính

Lặp lại các Phase dưới đây. Sau mỗi vòng in: `=== VÒNG N/5 ===`

---

## Phase 1 — BUILD

Chạy build thực tế và đọc output:

```bash
pnpm --filter api build 2>&1 | tail -20
```

```bash
pnpm --filter portal build 2>&1 | tail -15
```

**Quy tắc:**
- Nếu thấy `compiled successfully` hoặc `webpack ... compiled` → BUILD PASS
- Nếu thấy `compiled with X errors` hoặc `Error` hoặc exit code ≠ 0 → BUILD FAIL
- Nếu BUILD FAIL → ghi nhận lỗi, nhảy thẳng Phase 4 (Fix), KHÔNG chạy Phase 2-3

---

## Phase 2 — RESTART & CHECK LOGS

Restart services và đọc logs ngay sau đó để bắt lỗi runtime:

```bash
pm2 restart ai-voice-api ai-voice-portal ai-voice-worker
```

Đợi 4 giây để process khởi động:

```bash
sleep 4
```

Đọc logs của từng service, tìm lỗi:

```bash
pm2 logs ai-voice-api --lines 30 --nostream 2>&1
```

```bash
pm2 logs ai-voice-worker --lines 30 --nostream 2>&1
```

```bash
pm2 logs ai-voice-portal --lines 20 --nostream 2>&1
```

**Tìm trong logs:**
- `Error:`, `ERROR`, `Traceback`, `EADDRINUSE`, `ECONNREFUSED` → SERVICE FAIL
- `Listening on`, `Application is running`, `Started server` → SERVICE OK
- `SyntaxError`, `ImportError`, `ModuleNotFoundError` → cần fix code
- `Cannot find module` → thiếu dependency hoặc import sai

Nếu service fail: ghi nhận lỗi từ logs, nhảy Phase 4.

---

## Phase 3 — TEST THỰC TẾ

Chỉ chạy khi Phase 1 và Phase 2 đều PASS.

### 3a. Python tests

```bash
cd /Users/hiendang/ai-voice/services/voice && uv run pytest tests/ -v --tb=short 2>&1 | tail -50
```

Đọc output:
- `X passed, Y failed` → ghi nhận số lượng
- Dòng `FAILED tests/xxx.py::test_yyy` → tên test đang fail
- Block `ERRORS` hoặc `AssertionError: ...` → nguyên nhân cụ thể

### 3b. API tests (nếu có)

```bash
pnpm --filter api test 2>&1 | tail -30
```

### 3c. Health check thực tế

```bash
curl -sf http://localhost:3001/api/v1/health && echo " → API OK" || echo " → API FAIL"
```

```bash
curl -sf http://localhost:8000/health && echo " → WORKER OK" || echo " → WORKER FAIL"
```

```bash
curl -sf -o /dev/null -w "Portal HTTP %{http_code}\n" http://localhost:3000
```

---

## Phase 4 — FIX

Dựa trên lỗi **thực tế** đọc được từ Phase 1-3:

### Đọc file lỗi trước khi sửa

Luôn đọc đúng file và đúng dòng được chỉ ra trong error:

```bash
# Ví dụ nếu lỗi ở apps/api/src/foo/bar.ts:45
# → Read file đó trước, hiểu context, rồi mới sửa
```

### Nguyên tắc fix

- Fix **đúng dòng** báo lỗi, không sửa lan rộng
- Với Python: dùng `dataclasses.replace()` nếu cần copy dataclass, không mutate
- Với TypeScript: không dùng `any` để che lỗi type thật sự
- Không xóa test để pass — chỉ fix implementation
- Nếu lỗi do dependency thiếu → `uv add <pkg>` hoặc `pnpm --filter <app> add <pkg>`

### Sau khi fix

Xác nhận file đã sửa đúng, rồi quay về **Phase 1** của vòng tiếp theo.

---

## Phase 5 — Quyết định

```
Tất cả Phase 1-3 PASS?
  └─ Có  → In DONE REPORT, kết thúc
  └─ Không
       └─ Vòng hiện tại < 5? → in tóm tắt vòng, quay Phase 1
       └─ Vòng = 5?          → in ESCALATION REPORT, dừng
```

### DONE REPORT

```
=== DEV-LOOP HOÀN TẤT ✓ (vòng N/5) ===

Build API:      PASS
Build Portal:   PASS
Python tests:   X passed, 0 failed
API health:     UP (HTTP 200)
Worker health:  UP (HTTP 200)

Files đã sửa:
  - path/to/file (lý do ngắn gọn)

→ Sẵn sàng commit.
```

### TÓM TẮT MỖI VÒNG (khi chưa xong)

```
=== VÒNG N/5 — còn lỗi ===
Lỗi gặp: [mô tả ngắn]
Đã sửa:  [file + thay đổi gì]
Tiếp tục vòng N+1...
```

### ESCALATION REPORT (hết 5 vòng)

```
=== DEV-LOOP ESCALATE (5/5 vòng) ===

Lỗi chưa fix được:
  [copy nguyên văn error message từ output thực tế]

Đã thử:
  [liệt kê những gì đã sửa qua 5 vòng]

Cần user quyết định:
  1. Tiếp tục /dev-loop ?
  2. Xem thủ công: [file cụ thể] ?
  3. Bỏ qua tạm và note lại?
```

---

## Dừng ngay (không loop) nếu

- Lỗi do **external**: DB down, Redis không chạy, `.env` thiếu key thật → báo user, không fix code
- Lỗi do **test sai logic** (test expect sai, không phải code sai) → báo user để confirm trước khi sửa test
- Lỗi lặp lại **y hệt** sau 2 vòng fix → đang loop vô nghĩa, escalate ngay
