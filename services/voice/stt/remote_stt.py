"""Remote STT engine — delegates transcription to an inference server over HTTP.

Drop-in replacement for `FasterWhisperSTT` / `SenseVoiceSTT`: exposes
`transcribe_pcm` (async — `audio/pipeline.py` detects coroutine functions).
"""

from __future__ import annotations

import logging

import httpx

from stt.faster_whisper_stt import STTResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


class RemoteSTTError(RuntimeError):
    """Raised when the remote inference server is unreachable or errors out."""


class RemoteSTT:
    """STT via a remote inference server accepting raw PCM16 bytes."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = _DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
        token: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._client_owned = client is None
        self._token = token
        if not token:
            logger.warning(
                "RemoteSTT configured without inference_server_token — requests to "
                "%s will be rejected with 401 once server-side auth is enabled",
                self._base_url,
            )
        logger.info("RemoteSTT ready (base_url=%s)", self._base_url)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def aclose(self) -> None:
        if self._client is not None and self._client_owned:
            await self._client.aclose()
            self._client = None

    async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        """POST raw int16 PCM → STTResult. Raises RemoteSTTError on transport failure."""
        if not pcm_bytes:
            return STTResult(text="", confidence=0.0, is_final=True)

        url = f"{self._base_url}/stt/transcribe"
        try:
            headers = {"Content-Type": "application/octet-stream", **self._auth_headers()}
            resp = await self._get_client().post(
                url,
                content=pcm_bytes,
                params={"sample_rate": sample_rate},
                headers=headers,
                timeout=self._timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise RemoteSTTError(
                f"Remote STT {url} returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RemoteSTTError(f"Remote STT {url} unreachable: {exc}") from exc
        except ValueError as exc:
            raise RemoteSTTError(f"Remote STT {url} returned invalid JSON: {exc}") from exc

        return STTResult(
            text=str(data.get("text") or ""),
            confidence=float(data.get("confidence") or 0.0),
            is_final=bool(data.get("is_final", True)),
            language=str(data.get("language") or "vi"),
            emotion=data.get("emotion"),
        )
