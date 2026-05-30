---
name: reload
description: "Rebuild và restart toàn bộ stack (API, Portal, Voice Worker) sau khi code xong. Dùng pm2 nếu đang chạy, fallback sang restart thủ công."
origin: local
---

# /reload — Restart toàn bộ hệ thống

Sau mỗi lần code xong, chạy skill này để build lại và reload tất cả services.

## Bước 1: Build kiểm tra

```bash
# Build API (NestJS)
pnpm --filter api build 2>&1 | tail -10

# Build Portal (Next.js)
pnpm --filter portal build 2>&1 | tail -10
```

Nếu build lỗi → DỪNG, báo lỗi cho user, KHÔNG restart.

## Bước 2: Restart qua pm2 (ưu tiên)

```bash
# Kiểm tra pm2 có đang chạy không
pm2 list 2>/dev/null | grep -E "ai-voice|online|stopped"
```

Nếu pm2 đang chạy:
```bash
pm2 restart ai-voice-api
pm2 restart ai-voice-portal
pm2 restart ai-voice-worker
pm2 logs --lines 20 --nostream
```

Nếu pm2 chưa start:
```bash
pm2 start ecosystem.config.cjs
pm2 logs --lines 20 --nostream
```

## Bước 3: Kiểm tra health

```bash
# Đợi 3s rồi check
sleep 3

# API health
curl -s http://localhost:3001/api/v1/health | head -c 200

# Voice Worker health
curl -s http://localhost:8000/health | head -c 200

# Portal
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

## Bước 4: Báo cáo kết quả

Sau khi chạy, output theo format:

```
RELOAD REPORT
=============
Build API:     [PASS/FAIL]
Build Portal:  [PASS/FAIL]
pm2 restart:   [OK / error message]

Health:
  API:          http://localhost:3001  [UP/DOWN]
  Portal:       http://localhost:3000  [UP/DOWN]
  Voice Worker: http://localhost:8000  [UP/DOWN]

Trạng thái: [SẴN SÀNG / CẦN XEM LẠI]
```

## Lưu ý

- Nếu chỉ thay đổi Python (`services/voice/`) → chỉ restart `ai-voice-worker` vì uvicorn có `--reload`
- Nếu chỉ thay đổi Portal → chỉ restart `ai-voice-portal`
- Nếu thay đổi API → luôn phải build trước khi restart
- Không cần restart nếu chỉ thay đổi `.env` hoặc file markdown

## Shortcut theo loại thay đổi

| Thay đổi | Lệnh |
|----------|------|
| API (NestJS) | `pnpm --filter api build && pm2 restart ai-voice-api` |
| Portal (Next.js) | `pm2 restart ai-voice-portal` |
| Voice Worker (Python) | `pm2 restart ai-voice-worker` |
| Toàn bộ | `pm2 restart all` |
