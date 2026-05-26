# Call Script Contract v0.1

Đây là spec kỹ thuật định nghĩa format kịch bản cuộc gọi AI cho hệ thống DoctorCheck AI Call.

## Mục đích

Định nghĩa cấu trúc dữ liệu chuẩn cho kịch bản cuộc gọi, được lưu trong PostgreSQL và phục vụ cho:
- **Script CMS** (Portal): DoctorCheck nhập và chỉnh sửa kịch bản
- **Voice Runtime** (Python): Thực thi kịch bản theo từng cuộc gọi

---

## Cấu trúc tổng thể

```json
{
  "id": "<uuid>",
  "version": "1.0.0",
  "campaign_id": "<uuid>",
  "direction": "inbound" | "outbound",
  "voice_profile": "linh_clone_v1",
  "entry_step": "greeting",
  "steps": [...],
  "intents": [...]
}
```

---

## Beat — Đơn vị phát âm nhỏ nhất

Mỗi câu nói được chia thành các **beat** để kiểm soát ngữ điệu và nhịp nói.

```json
{
  "text": "Xin chào,",
  "pause_after": "breath",
  "role": "agent"
}
```

### Pause Tiers

| Tier | Duration | Khi nào dùng |
|------|----------|-------------|
| `none` | 0ms | Không dừng |
| `micro` | 80ms | Phân tách âm tiết nhỏ |
| `short` | 150ms | Dấu phẩy |
| `breath` | 250ms | Ngắt nhẹ tự nhiên |
| `medium` | 400ms | Dấu chấm phẩy, đoạn ngắn |
| `long` | 700ms | Dấu chấm, kết câu |
| `turn` | 1000ms | Chờ phản hồi từ khách |

### Beat Roles

| Role | Ý nghĩa |
|------|---------|
| `agent` | Lời của AI agent (phát âm) |
| `system` | Metadata, không phát âm |
| `silent` | Khoảng im lặng có chủ đích |

---

## Variant — Biến thể câu nói

Mỗi step phải có **ít nhất 1 variant**. Reprompt (khi khách không trả lời) phải có **ít nhất 3 variants** để tránh lặp.

```json
{
  "id": "v1",
  "beats": [
    {"text": "Xin chào,", "pause_after": "breath"},
    {"text": "tôi là Linh từ phòng khám DoctorCheck.", "pause_after": "long"}
  ]
}
```

---

## Step — Bước trong kịch bản

```json
{
  "id": "greeting",
  "type": "speak_listen",
  "variants": [...],
  "reprompt_variants": [...],
  "transitions": [
    {"when": "intent == 'book_appointment'", "goto": "collect_date"},
    {"when": "intent == 'cancel'", "goto": "handle_cancel"}
  ],
  "fallback_goto": "handoff",
  "max_no_match": 3
}
```

### Step Types

| Type | Hành vi |
|------|---------|
| `speak` | Phát lời, không chờ phản hồi |
| `speak_listen` | Phát lời, chờ và nhận intent từ khách |
| `hold` | Giữ máy (hold music / im lặng) |
| `handoff` | Chuyển máy tới tổng đài viên thật |
| `hangup` | Kết thúc cuộc gọi |

---

## Intent Catalog

Danh sách intent được nhận dạng trong campaign:

```json
{
  "intent": "book_appointment",
  "examples": [
    {"text": "tôi muốn đặt lịch khám"},
    {"text": "đặt hẹn ngày mai"},
    {"text": "cho tôi đặt lịch", "slots": {"date": "tomorrow"}}
  ],
  "slots": ["date", "time", "specialty"]
}
```

---

## Lint Rules

Các rule bắt buộc khi validate kịch bản (chạy tại `POST /scripts/validate`):

| Code | Mô tả |
|------|-------|
| L001 | Step id phải là `snake_case` |
| L002 | `entry_step` phải tồn tại trong danh sách `steps` |
| L003 | Mọi `goto` trong `transitions` phải trỏ tới step tồn tại |
| L004 | `fallback_goto` (nếu có) phải trỏ tới step tồn tại |
| L005 | `speak_listen` step bắt buộc có `reprompt_variants` với ≥3 variants |
| L006 | Không có step nào unreachable (ngoại trừ entry_step) |
| L007 | Mọi `handoff` step phải có `reason` trong data |
| L008 | Tổng số steps ≤ 50 per campaign |

---

## Ví dụ: Booking Inbound

Xem `scripts/examples/booking_inbound_v1.json` để tham khảo campaign mẫu.

---

## Versioning

- Phiên bản kịch bản theo semver: `MAJOR.MINOR.PATCH`
- `MAJOR`: Thay đổi flow cơ bản (thêm/xóa steps, đổi entry_step)
- `MINOR`: Thêm intent mới, thêm variant
- `PATCH`: Sửa text, sửa pause tier
- Chỉ có 1 version `published` tại một thời điểm per campaign
- Không xóa version cũ — archive thay thế
