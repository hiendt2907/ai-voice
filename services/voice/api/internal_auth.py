"""Header xác thực cho các lời gọi service-to-service tới `/internal/*` của NestJS.

`/internal/*` từng KHÔNG có xác thực nào và lộ thẳng ra internet qua ingress
(`https://api.aivoice.asia/api/v1/internal/nlu/export` trả 200 cho bất kỳ ai).
Sau khi NestJS gắn `InternalAuthGuard`, mọi lời gọi từ voice worker phải kèm
header `x-internal-key`, nếu không sẽ nhận 401 và toàn bộ luồng nạp NLU/KB/
system-settings lúc khởi động sẽ gãy.

Đặt ở MỘT chỗ dùng chung thay vì tự dựng header tại từng call site: trước đây
chỉ `ws.py::_post_call_events` gửi header, 6 call site còn lại thì không — đúng
dạng lỗi "mỗi nơi một bản" đã cắn dự án này nhiều lần (xem CLAUDE.md).
"""

from __future__ import annotations

from api.config import Settings

# Đọc một lần lúc import: Settings() là pydantic-settings đọc từ env, không đổi
# trong vòng đời tiến trình, và các call site nằm trên critical path của cuộc gọi.
_settings = Settings()


def internal_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Trả về header cho lời gọi `/internal/*`, kèm `x-internal-key` nếu có cấu hình.

    Key rỗng → không gửi header. Cố ý không ném lỗi ở đây: môi trường dev cục bộ
    chạy NestJS chưa bật guard vẫn phải dùng được, và phía NestJS mới là nơi
    quyết định từ chối hay không.
    """
    key = _settings.service_api_key or _settings.internal_api_key
    headers = dict(extra or {})
    if key:
        headers["x-internal-key"] = key
    return headers
