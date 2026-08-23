"""Generic async LLM client using the OpenAI-compatible chat API.

Works with any OpenAI-compatible endpoint:
  - Ollama:     base_url="http://localhost:11434/v1", api_key="ollama"
  - DashScope:  base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
  - OpenAI:     base_url="https://api.openai.com/v1"

The api_key is sent in the Authorization header; Ollama ignores it.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_MODEL = "qwen2.5:latest"

# Số lần lỗi liên tiếp trước khi tạm ngắt một model.
_BREAKER_THRESHOLD = 2
# Ngắt tạm cho lỗi có thể tự khỏi (503, timeout, mạng).
_BREAKER_RESET_S = 120.0
# Ngắt dài cho lỗi cấu hình/quyền, sẽ không tự khỏi trong vài phút:
# 403 "requires a paid account", 404 model không tồn tại. Thử lại mỗi lượt
# thoại chỉ tổ đốt thêm một round-trip cho mỗi câu khách nói.
_BREAKER_PERMANENT_S = 1800.0
_PERMANENT_STATUS = frozenset({400, 401, 403, 404, 422})


class _ModelBreaker:
    """Cầu dao theo từng model, để model chết không bị thử lại mỗi lượt."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def is_open(self, model: str) -> bool:
        until = self._open_until.get(model, 0.0)
        if until and time.monotonic() < until:
            return True
        if until:  # hết hạn ngắt → cho thử lại từ đầu
            self._open_until.pop(model, None)
            self._failures.pop(model, None)
        return False

    def record_success(self, model: str) -> None:
        self._failures.pop(model, None)
        self._open_until.pop(model, None)

    def record_failure(self, model: str, permanent: bool = False) -> None:
        if permanent:
            self._open_until[model] = time.monotonic() + _BREAKER_PERMANENT_S
            logger.warning("LLM model %s tạm ngắt %.0fs (lỗi cấu hình/quyền)", model, _BREAKER_PERMANENT_S)
            return
        n = self._failures.get(model, 0) + 1
        self._failures[model] = n
        if n >= _BREAKER_THRESHOLD:
            self._open_until[model] = time.monotonic() + _BREAKER_RESET_S
            logger.warning("LLM model %s tạm ngắt %.0fs sau %d lỗi", model, _BREAKER_RESET_S, n)

    def status(self) -> dict[str, str]:
        return {
            m: "open" for m in self._open_until if self.is_open(m)
        }


def _is_permanent(exc: Exception) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _PERMANENT_STATUS
    )


class LLMClient:
    """Async wrapper quanh /chat/completions (OpenAI-compatible), có fallback model.

    Nhận một danh sách model thử theo thứ tự. Model lỗi bị cầu dao tạm ngắt nên
    không bị thử lại ở mọi lượt thoại — đây là điểm mấu chốt: mỗi lần thử một
    model chết là cộng thêm một round-trip vào độ trễ của CÂU KHÁCH ĐANG NÓI.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        api_key: str = "ollama",
        timeout_s: float = 10.0,
        fallback_models: list[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # model chính luôn đứng đầu; loại trùng nhưng giữ nguyên thứ tự ưu tiên.
        ordered = [model, *(fallback_models or [])]
        self._models: list[str] = list(dict.fromkeys(m for m in ordered if m))
        self._breaker = _ModelBreaker()
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._timeout_s = timeout_s
        self._client = httpx.AsyncClient(timeout=timeout_s, headers=self._headers)

    @property
    def _model(self) -> str:
        """Model đang ưu tiên — giữ tên cũ cho code/test đã tham chiếu."""
        for m in self._models:
            if not self._breaker.is_open(m):
                return m
        return self._models[0] if self._models else _DEFAULT_MODEL

    def model_status(self) -> dict[str, str]:
        return {m: ("open" if self._breaker.is_open(m) else "closed") for m in self._models}

    def _candidates(self) -> list[str]:
        live = [m for m in self._models if not self._breaker.is_open(m)]
        # Tất cả đều bị ngắt → vẫn phải thử, thà chậm còn hơn từ chối trả lời.
        return live or list(self._models)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> str:
        """One-shot completion, tự chuyển model khi model hiện tại hỏng."""
        last_exc: Exception | None = None
        for model in self._candidates():
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
            }
            try:
                resp = await self._client.post(
                    f"{self._base_url}/chat/completions", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                content = str(data["choices"][0]["message"]["content"])
                if not content.strip():
                    # HTTP 200 nhưng content rỗng (đã gặp thật với z-ai/glm-4.6).
                    # Coi là hỏng, nếu không tầng trên nhận chuỗi rỗng và xử lý
                    # như "model không hiểu" — sai bản chất và không ai biết.
                    raise ValueError("empty content")
                self._breaker.record_success(model)
                return content
            except Exception as exc:
                permanent = _is_permanent(exc)
                self._breaker.record_failure(model, permanent=permanent)
                logger.warning("LLM %s lỗi (%s), thử model kế tiếp", model, exc)
                last_exc = exc
        raise RuntimeError(f"Tất cả model LLM đều lỗi: {last_exc}") from last_exc

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """Streaming completion, có fallback TRƯỚC token đầu tiên.

        Đã phát token ra ngoài rồi thì không đổi model được nữa — ghép nửa câu
        của hai model sẽ ra câu vô nghĩa đọc cho khách nghe. Lỗi giữa chừng
        được ném lên để tầng trên xử lý.
        """
        last_exc: Exception | None = None
        for model in self._candidates():
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
                "temperature": temperature,
            }
            emitted = False
            try:
                async with self._client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        if token := delta.get("content", ""):
                            emitted = True
                            yield token
                if not emitted:
                    raise ValueError("empty stream")
                self._breaker.record_success(model)
                return
            except Exception as exc:
                if emitted:
                    # Đứt giữa chừng: không được thử model khác.
                    self._breaker.record_failure(model)
                    raise
                permanent = _is_permanent(exc)
                self._breaker.record_failure(model, permanent=permanent)
                logger.warning("LLM stream %s lỗi (%s), thử model kế tiếp", model, exc)
                last_exc = exc
        raise RuntimeError(f"Tất cả model LLM đều lỗi: {last_exc}") from last_exc

    async def aclose(self) -> None:
        await self._client.aclose()


class ClaudeNLUClient:
    """NLU via Anthropic Claude — faster and more accurate than local Ollama.

    Uses claude-haiku-4-5-20251001 by default: fast, cheap, sufficient for
    slot extraction and intent classification in Vietnamese call flows.

    Implements the same ``chat`` interface as ``LLMClient`` so it can be used
    as a drop-in inside ``LLMNLUClassifier``.
    """

    model: str = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str, timeout_s: float = 10.0) -> None:
        import anthropic  # lazy import — optional dep

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._timeout_s = timeout_s
        logger.info("ClaudeNLUClient initialized (model=%s)", self.model)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> str:
        """One-shot completion compatible with LLMClient.chat interface.

        Separates the system message (if any) from the conversation turns
        because Anthropic API uses a dedicated ``system`` parameter.
        """
        system_parts: list[str] = []
        turns: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                turns.append({"role": msg["role"], "content": msg["content"]})

        system_text = "\n\n".join(system_parts) or None

        import anthropic as _anthropic  # noqa: PLC0415

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=512,
                temperature=temperature,
                system=system_text,
                messages=turns,  # type: ignore[arg-type]
            )
            content = response.content[0]
            if hasattr(content, "text"):
                return str(content.text)
            return ""
        except _anthropic.APIError as exc:
            logger.error("ClaudeNLUClient API error: %s", exc)
            raise

    async def aclose(self) -> None:
        await self._client.close()
