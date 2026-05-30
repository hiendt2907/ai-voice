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
from collections.abc import AsyncGenerator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_MODEL = "qwen2.5:latest"


class LLMClient:
    """Thin async wrapper around /chat/completions (OpenAI-compatible)."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        api_key: str = "ollama",
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._timeout_s = timeout_s
        self._client = httpx.AsyncClient(timeout=timeout_s, headers=self._headers)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> str:
        """One-shot completion. Returns the assistant content string."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        resp = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """Streaming completion — yields token chunks as they arrive."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
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
                    yield token

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
