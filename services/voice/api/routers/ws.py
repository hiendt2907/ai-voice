"""Full streaming call pipeline WebSocket endpoint.

Architecture:
  accept WS
    ├─ pipeline_task:  AudioPipeline.process() → transcript_queue
    ├─ redis_sub_task: Redis answer:{sessionId} → answer_queue
    └─ turn_task:      transcript_queue + answer_queue → filler → RAG/FSM → TTS → audio

Protocol supports two modes:
  • REAL  (audio_frame events): μ-law frames in base64 → AudioPipeline → STT → turns
  • MOCK  (utterance events):   pre-transcribed text for testing / CI
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.config import Settings
from audio.pipeline import AudioPipeline
from cloudfone.protocol import (
    AudioChunkPayload,
    BeatPayload,
    HangupPayload,
    HandoffPayload,
    InboundEvent,
    OutboundEvent,
    QuestionAnsweredMessage,
    StartMessage,
    UtteranceMessage,
)
from llm.client import LLMClient
from llm.nlu import LLMNLUClassifier
from runtime.executor import async_process_turn, create_session
from runtime.session import PendingQuestion, SessionState, TranscriptEntry
from tts.elevenlabs_tts import ElevenLabsTTS
from tts.fillers import FillerSelector
from tts.streamer import stream_step_beats
from tts.synthesis import GwenTTS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

_settings = Settings()

_VN_TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh


def _build_tts() -> ElevenLabsTTS | GwenTTS | None:
    if not _settings.use_real_tts:
        return None
    return _build_tts_forced()


def _build_tts_forced() -> ElevenLabsTTS | GwenTTS | None:
    """Build TTS ignoring use_real_tts flag. Returns None if credentials not available."""
    try:
        if _settings.tts_engine == "elevenlabs":
            if not _settings.elevenlabs_api_key:
                logger.warning("use_real_tts requested but ELEVENLABS_API_KEY not set → beat mode")
                return None
            logger.info(
                "TTS (forced): ElevenLabs voice=%s model=%s",
                _settings.elevenlabs_voice_id,
                _settings.elevenlabs_model_id,
            )
            return ElevenLabsTTS(
                api_key=_settings.elevenlabs_api_key,
                voice_id=_settings.elevenlabs_voice_id,
                model_id=_settings.elevenlabs_model_id,
                stability=_settings.elevenlabs_stability,
                similarity_boost=_settings.elevenlabs_similarity_boost,
                style=_settings.elevenlabs_style,
                use_speaker_boost=_settings.elevenlabs_use_speaker_boost,
            )
        # gwen-tts: only attempt if ref audio is configured
        if not _settings.tts_ref_audio:
            logger.warning("use_real_tts requested but TTS_REF_AUDIO not set → beat mode")
            return None
        logger.info("TTS (forced): gwen-tts model=%s", _settings.tts_model_id)
        return GwenTTS(
            model_id=_settings.tts_model_id,
            ref_audio_path=_settings.tts_ref_audio,
            device=_settings.tts_device,
        )
    except Exception as exc:
        logger.warning("Failed to build TTS on-demand: %s — falling back to beat mode", exc)
        return None


# Module-level singleton — shared across connections (avoid per-connection model reload)
_tts = _build_tts()


def _build_nlu() -> LLMNLUClassifier | None:
    if not _settings.use_llm_nlu:
        return None
    client = LLMClient(
        base_url=_settings.llm_base_url,
        model=_settings.llm_model,
        api_key=_settings.llm_api_key,
        timeout_s=_settings.llm_timeout_s,
    )
    return LLMNLUClassifier(client)


async def _send_beat(ws: WebSocket, beat: BeatPayload) -> None:
    await ws.send_json(beat.to_dict())


async def _send_audio(ws: WebSocket, pcm_bytes: bytes, turn: int) -> None:
    chunk = AudioChunkPayload(data=base64.b64encode(pcm_bytes).decode(), turn=turn)
    await ws.send_json(chunk.to_dict())


def _index_steps(script: dict) -> dict[str, dict]:
    return {s["id"]: s for s in script.get("steps", [])}


def _pick_variant(step: dict, no_match_count: int) -> dict:
    if no_match_count > 0 and step.get("reprompt_variants"):
        reprompts: list[dict] = step["reprompt_variants"]
        idx = (no_match_count - 1) % len(reprompts)
        return reprompts[idx]
    variants: list[dict] = step.get("variants", [])
    return variants[0] if variants else {}


def _after_hours_hint() -> str:
    now = datetime.now(_VN_TZ)
    if now.hour >= 22 or now.hour < 7:
        return "sáng mai"
    return "khoảng 15 phút nữa"


@router.websocket("/call")
async def call_ws(ws: WebSocket, script_id: str = "") -> None:
    """Streaming call WebSocket. Supports real audio (audio_frame) and mock (utterance) modes."""
    await ws.accept()

    state: SessionState | None = None
    script: dict[str, Any] = {}
    steps: dict[str, dict] = {}
    turn = 0
    started_at = time.time()

    try:
        tts = ws.app.state.tts or _tts  # prefer app.state.tts (has redis for metrics)
    except AttributeError:
        tts = _tts  # tests may not have app.state
    nlu = _build_nlu()
    filler_selector = FillerSelector()

    tts_interrupt = asyncio.Event()
    tts_active = False
    call_ended = asyncio.Event()

    transcript_queue: asyncio.Queue[str] = asyncio.Queue()
    answer_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    # Call metadata (set on START, used in Phase 4 call-events webhook)
    session_id: str = ""
    campaign_id: str | None = None
    script_version_id: str | None = None
    caller_number: str | None = None
    caller_direction: str = "inbound"

    # Phase 2: track last RAG score for call metadata
    last_rag_score: float | None = None
    barge_in_count: int = 0

    # Active background tasks
    pipeline: "AudioPipeline | None" = None
    pipeline_task: asyncio.Task | None = None
    redis_sub_task: asyncio.Task | None = None
    pending_question_tasks: list[asyncio.Task] = []

    # ── helpers ────────────────────────────────────────────────────────────────

    async def _stream_step(
        ws: WebSocket,
        step: dict,
        slots: dict,
        no_match: int,
        cur_turn: int,
        t_start: float,
    ) -> None:
        # Phase 5.1: notify VAD of TTS start for half-duplex suppression
        if pipeline is not None:
            pipeline._vad.on_tts_start()

        try:
            if tts:
                from tts.audio_stream import BeatsAudioStream  # noqa: PLC0415

                variant = _pick_variant(step, no_match)
                beats: list[dict] = variant.get("beats", [])
                if hasattr(tts, "stream_step"):
                    gen = await tts.stream_step(beats, slots, tts_interrupt)  # type: ignore[union-attr]
                else:
                    gen = BeatsAudioStream(tts, tts_interrupt).stream(beats, slots)
                first = True
                async for chunk in gen:
                    if first:
                        ttfa_ms = round((time.perf_counter() - t_start) * 1000, 1)
                        logger.info("TTFA: %.1f ms", ttfa_ms)
                        first = False
                    await _send_audio(ws, chunk, cur_turn)
            else:
                async for beat in stream_step_beats(step, slots, no_match, cur_turn, t_start):
                    if tts_interrupt.is_set():
                        break
                    await _send_beat(ws, beat)
        finally:
            # Phase 5.1: release half-duplex suppression after TTS ends
            if pipeline is not None:
                pipeline._vad.on_tts_end()

    async def _tts_say(text: str, cur_turn: int, t_start: float) -> None:
        """Synthesize and send a single text string."""
        beat = BeatPayload(
            text=text,
            pause_ms=500,
            turn=cur_turn,
            step_id=state.current_step_id if state else "",
            ttfa_ms=round((time.perf_counter() - t_start) * 1000, 1),
        )
        await _send_beat(ws, beat)
        if tts:
            audio = await tts.synthesize(text)
            await _send_audio(ws, audio, cur_turn)

    # ── Phase 2: RAG-assisted turn ────────────────────────────────────────────

    async def _rag_turn(utterance: str, t_start: float) -> None:
        """Handle utterance for rag_assisted execution mode (Phase 2)."""
        nonlocal state, turn, tts_active, last_rag_score

        from rag import store as rag_store  # noqa: PLC0415

        tts_active = True
        tts_interrupt.clear()
        turn += 1

        # Concurrent filler — stream while RAG embedding runs
        filler_text = filler_selector.next("thinking")
        filler_task = asyncio.create_task(
            _emit_filler(filler_text, turn, t_start, state.current_step_id if state else "")
        )

        # Phase 2.3: gender detect from accumulated PCM (use slot if already set)
        gender = state.slots.get("gender", "unknown") if state else "unknown"  # type: ignore[union-attr]

        # Embed and search
        try:
            from rag.embedder import embed_query  # noqa: PLC0415

            loop = asyncio.get_running_loop()
            query_emb = await loop.run_in_executor(None, embed_query, utterance)
            linked_tags: list[str] = script.get("linkedKbTags", [])
            result = rag_store.search(
                query_emb,
                gender=gender,
                linked_kb_tags=linked_tags,
                max_threshold=_settings.rag_confidence_default,
                campaign_id=campaign_id,
            )
        except Exception as exc:
            logger.warning("RAG search error: %s", exc)
            result = None

        await filler_task  # ensure filler finishes before real response

        if result is not None:
            last_rag_score = result.score
            logger.info("RAG hit: score=%.3f article=%s", result.score, result.article.id)
            await _tts_say(result.answer, turn, t_start)
        else:
            # Phase 2.5: below confidence threshold → Phase 3 handoff
            last_rag_score = 0.0
            fallback_gender = gender if gender in ("male", "female") else "unknown"
            fallback_msg = script.get("ragFallbackMessage", rag_store.fallback_text(fallback_gender))
            await _tts_say(fallback_msg, turn, t_start)

            # Phase 3: escalate to Telegram
            if state:
                await _escalate_question(utterance)

        tts_active = False

    # ── Phase 3: Expert Handoff ───────────────────────────────────────────────

    async def _escalate_question(utterance: str) -> None:
        """Send to Telegram + schedule timeout (Phase 3)."""
        nonlocal state
        if state is None:
            return

        question_id = str(uuid.uuid4())
        q = PendingQuestion(
            question_id=question_id,
            question_text=utterance,
            timeout_seconds=_settings.question_timeout_seconds,
        )
        state = state.with_pending_question(q)

        callback_url = (
            f"{_settings.voice_worker_base_url}/callbacks/question"
            f"/{session_id}/{question_id}"
        )

        # Send to Telegram (non-fatal)
        if _settings.notify_platform == "telegram" and _settings.telegram_bot_token:
            try:
                from notify.telegram import TelegramNotifier  # noqa: PLC0415

                notifier = TelegramNotifier(
                    bot_token=_settings.telegram_bot_token,
                    group_id=_settings.telegram_group_id,
                )
                await notifier.send(utterance, session_id, callback_url)
                await notifier.aclose()
            except Exception as exc:
                logger.warning("Telegram notify failed: %s", exc)

        # Start 60-second timeout
        task = asyncio.create_task(_question_timeout(question_id, utterance))
        pending_question_tasks.append(task)

    async def _question_timeout(question_id: str, question_text: str) -> None:
        """After timeout, inject follow-up template (Phase 3.7–3.9)."""
        nonlocal state
        timeout_s = _settings.question_timeout_seconds
        await asyncio.sleep(timeout_s)

        if call_ended.is_set() or state is None:
            return
        if not any(q.question_id == question_id for q in state.pending_questions):
            return  # already answered

        state = state.without_pending_question(question_id)
        time_hint = _after_hours_hint()
        followup = (
            f"Dạ về câu hỏi vừa rồi, bác sĩ sẽ liên hệ lại {time_hint} ạ. "
            "Bác có cần đặt lịch khám ngay bây giờ không ạ?"
        )
        logger.info("Question %s timed out after %ds, injecting follow-up", question_id, timeout_s)
        await _tts_say(followup, turn, time.perf_counter())

    async def _inject_answer(question_id: str, answer_text: str) -> None:
        """Inject doctor's answer into the ongoing conversation (Phase 3.5)."""
        nonlocal state
        if state is None:
            return

        state = state.without_pending_question(question_id)
        full_text = f"Dạ về câu hỏi ban nãy, {answer_text}"
        logger.info("Injecting answer for question_id=%s", question_id)
        await _tts_say(full_text, turn, time.perf_counter())

    # ── Phase 3: Redis answer subscriber ─────────────────────────────────────

    async def _redis_answer_subscriber(sid: str) -> None:
        """Subscribe to Redis answer:{sessionId} for doctor replies (Phase 3.4)."""
        channel = f"answer:{sid}"
        try:
            redis: aioredis.Redis = aioredis.from_url(  # type: ignore[type-arg]
                _settings.redis_url, decode_responses=True
            )
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe(channel)
                logger.info("Redis: subscribed to %s", channel)
                async for message in pubsub.listen():
                    if call_ended.is_set():
                        break
                    if message["type"] != "message":
                        continue
                    payload: str = message["data"]
                    parts = payload.split("|", 1)
                    if len(parts) == 2:
                        qid, ans = parts
                        await answer_queue.put((qid, ans))
                        logger.info("Answer received for question_id=%s", qid)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Redis subscriber error: %s", exc)
        finally:
            try:
                await redis.aclose()
            except Exception:
                pass

    # ── Main turn handler ─────────────────────────────────────────────────────

    def _script_exec_mode() -> str:
        """Determine execution mode: explicit field takes priority, then infer from type."""
        explicit = script.get("execution_mode")
        if explicit:
            return str(explicit)
        # Legacy: type == "ai_driven" with no steps → rag_assisted
        if script.get("type") == "ai_driven":
            return "rag_assisted"
        return "fsm"

    _QUESTION_RE = re.compile(
        r"\?$"
        r"|\b(bao nhiêu|mấy tiếng|như thế nào|ra sao|thế nào|là gì|ở đâu|khi nào|làm gì|cần gì)\b"
        r"|\bcó\b.{0,25}\bkhông\b"
        r"|\b(giá|chi phí|phí|chuẩn bị|nhịn ăn|đau không|an toàn|nguy hiểm|kết quả|bảo hiểm"
        r"|mất bao|sau nội soi|sau khi|thuốc|tác dụng)\b",
        re.IGNORECASE | re.DOTALL,
    )

    async def _fsm_rag_intercept(utterance: str, cur_turn: int, t_start: float) -> bool:
        """Try RAG for mid-FSM questions. Returns True if RAG answered (don't increment no_match)."""
        nonlocal last_rag_score
        if not _QUESTION_RE.search(utterance):
            return False
        try:
            from rag import store as rag_store  # noqa: PLC0415
            from rag.embedder import embed_query  # noqa: PLC0415

            loop = asyncio.get_running_loop()
            query_emb = await loop.run_in_executor(None, embed_query, utterance)
            gender = state.slots.get("gender", "unknown") if state else "unknown"  # type: ignore[union-attr]
            linked_tags: list[str] = script.get("linkedKbTags", [])
            result = rag_store.search(
                query_emb,
                gender=gender,  # type: ignore[arg-type]
                linked_kb_tags=linked_tags or None,
                max_threshold=_settings.rag_confidence_default,
                campaign_id=campaign_id,
            )
        except Exception as exc:
            logger.warning("FSM RAG intercept error: %s", exc)
            return False

        if result is None:
            return False

        last_rag_score = result.score
        logger.info("FSM RAG intercept: score=%.3f article=%s", result.score, result.article.id)
        await _tts_say(result.answer, cur_turn, t_start)
        return True

    async def _emit_filler(filler_text: str, cur_turn: int, t_start: float, cur_step_id: str) -> None:
        """Synthesize and send a filler sound — runs concurrently with turn processing."""
        if tts:
            filler_pcm = await tts.synthesize(filler_text)
            await _send_audio(ws, filler_pcm, cur_turn)
        else:
            filler_beat = BeatPayload(
                text=filler_text, pause_ms=0, turn=cur_turn,
                step_id=cur_step_id,
                ttfa_ms=round((time.perf_counter() - t_start) * 1000, 1),
            )
            await _send_beat(ws, filler_beat)

    async def process_utterance(utterance: str, t_start: float) -> None:
        nonlocal state, turn, tts_active

        if state is None:
            return

        if _script_exec_mode() == "rag_assisted":
            await _rag_turn(utterance, t_start)
            return

        # FSM mode (default)
        tts_active = True
        tts_interrupt.clear()
        turn += 1

        # Read on_receive filler hint from current step (script-level override)
        cur_step = steps.get(state.current_step_id, {})
        step_filler_ctx: str = cur_step.get("on_receive", {}).get("filler_context", "thinking")

        filler_text = filler_selector.next(step_filler_ctx)  # type: ignore[arg-type]

        # CONCURRENT: filler synthesis + turn processing run in parallel
        filler_task = asyncio.create_task(
            _emit_filler(filler_text, turn, t_start, state.current_step_id)
        )
        result = await async_process_turn(state, script, utterance, nlu)

        # If result suggests a better filler context, stream a second filler
        # only if processing finished before the first filler (rare, fast NLU case)
        await filler_task

        state = result.state

        if result.is_handoff:
            step = steps.get(state.current_step_id, {})
            await _stream_step(ws, step, dict(state.slots), 0, turn, t_start)
            await ws.send_json(HandoffPayload(step_id=state.current_step_id).to_dict())
            call_ended.set()
            return

        if result.is_completed:
            step = steps.get(state.current_step_id, {})
            await _stream_step(ws, step, dict(state.slots), 0, turn, t_start)
            await ws.send_json(HangupPayload(step_id=state.current_step_id).to_dict())
            call_ended.set()
            return

        # Hybrid FSM+RAG: no transition matched → intercept with RAG before reprompting
        if result.next_step_id is None and not result.is_handoff and not result.is_completed:
            rag_answered = await _fsm_rag_intercept(utterance, turn, t_start)
            if rag_answered:
                # Re-speak current step prompt to resume booking flow
                step = steps.get(state.current_step_id, {})
                no_match = state.get_no_match_count(state.current_step_id)
                await _stream_step(ws, step, dict(state.slots), no_match, turn, t_start)
                tts_active = False
                return

        if result.next_step_id is not None:
            step = steps.get(result.next_step_id, {})
            no_match = 0
        else:
            step = steps.get(state.current_step_id, {})
            no_match = state.get_no_match_count(state.current_step_id)

        await _stream_step(ws, step, dict(state.slots), no_match, turn, t_start)

        landed_type = step.get("type", "")
        if landed_type in ("speak", "hangup"):
            await ws.send_json(HangupPayload(step_id=step.get("id", "")).to_dict())
            call_ended.set()
            return
        if landed_type == "handoff":
            await ws.send_json(HandoffPayload(step_id=step.get("id", "")).to_dict())
            call_ended.set()
            return

        tts_active = False

    # ── Turn handler task: drains transcripts + injected answers ─────────────

    async def turn_handler() -> None:
        while not call_ended.is_set():
            # Drain pending doctor answers first
            while not answer_queue.empty():
                qid, ans = answer_queue.get_nowait()
                await _inject_answer(qid, ans)

            try:
                text = await asyncio.wait_for(transcript_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            t0 = time.perf_counter()
            await process_utterance(text, t0)

    turn_task = asyncio.create_task(turn_handler())

    # ── Phase 4: POST call-events to NestJS on hangup ────────────────────────

    async def _post_call_events() -> None:
        if state is None:
            return
        transcript_dicts = [
            {
                "step_id": e.step_id,
                "role": e.role,
                "text": e.text,
                "intent": e.intent,
            }
            for e in state.transcript
        ]
        payload: dict[str, Any] = {
            "sessionId": state.session_id,
            "campaignId": campaign_id,
            "scriptVersionId": script_version_id,
            "direction": caller_direction,
            "callerNumber": caller_number,
            "status": state.status if state.status in ("completed", "handoff") else "error",
            "transcript": transcript_dicts,
            "slots": dict(state.slots),
            "finalStepId": state.current_step_id,
            "durationSeconds": round(time.time() - started_at),
            "startedAt": datetime.fromtimestamp(started_at).isoformat(),
            "endedAt": datetime.now().isoformat(),
            "meta": {
                "bargeInCount": barge_in_count,
                "noMatchCounts": dict(state.no_match_counts),
                "lastRagScore": last_rag_score,
            },
        }
        try:
            headers: dict[str, str] = {}
            if _settings.service_api_key:
                headers["x-internal-key"] = _settings.service_api_key
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(_settings.nestjs_webhook_url, json=payload, headers=headers)
                resp.raise_for_status()
                logger.info("Call-events posted: session=%s status=%s", state.session_id, state.status)
        except Exception as exc:
            logger.warning("Failed to post call-events: %s", exc)

    # ── Main WS event loop ────────────────────────────────────────────────────

    try:
        async for raw in ws.iter_json():
            if call_ended.is_set():
                break

            event_name: str = raw.get("event", "")

            if event_name == InboundEvent.START:
                # Per-connection TTS control from Simulator toggle or START payload.
                # use_real_tts=True → force-enable TTS (build if not already active).
                # use_real_tts=False → explicitly disable TTS for this connection (beat mode).
                client_wants_tts = raw.get("use_real_tts")
                if client_wants_tts is True and not tts:
                    tts = getattr(ws.app.state, "tts", None) or _build_tts_forced()
                    if tts:
                        logger.info("Per-connection TTS override: built %s", type(tts).__name__)
                elif client_wants_tts is False:
                    tts = None
                    logger.info("Per-connection TTS disabled by client (beat mode)")

                logger.info(
                    "START: campaign=%s tts=%s",
                    raw.get("campaign_id"),
                    type(tts).__name__ if tts else "mock(beat)",
                )
                start = StartMessage.from_dict(raw)
                session_id = start.session_id or str(uuid.uuid4())
                campaign_id = start.campaign_id
                script_version_id = start.script_version_id
                caller_number = start.caller_number
                caller_direction = start.direction

                script = raw.get("script", {})
                steps = _index_steps(script)
                state = create_session(script)
                started_at = time.time()

                # Phase 1: Start AudioPipeline background task
                try:
                    stt = ws.app.state.stt
                except AttributeError:
                    stt = None  # tests may not have app.state

                if stt is not None:
                    pipeline = AudioPipeline(stt)

                    async def _drain_pipeline(p: AudioPipeline) -> None:
                        async for result in p.process():
                            if result.text:
                                await transcript_queue.put(result.text)
                                logger.info(
                                    "STT transcript: %r (conf=%.2f)",
                                    result.text,
                                    result.confidence,
                                )

                    pipeline_task = asyncio.create_task(_drain_pipeline(pipeline))

                # Phase 3: Subscribe to Redis for doctor answers
                redis_sub_task = asyncio.create_task(_redis_answer_subscriber(session_id))

                # Send greeting
                t0 = time.perf_counter()
                if _script_exec_mode() == "rag_assisted":
                    # ai_driven scripts: greeting is a plain text field, no steps
                    greeting_text = script.get("greeting", "Dạ, DoctorCheck xin nghe ạ")
                    if greeting_text:
                        await _tts_say(greeting_text, turn, t0)
                else:
                    # FSM scripts: first step drives the greeting
                    step = steps.get(state.current_step_id, {})
                    await _stream_step(ws, step, {}, 0, turn, t0)
                    if step.get("type") in ("speak", "hangup"):
                        await ws.send_json(HangupPayload(step_id=state.current_step_id).to_dict())
                        call_ended.set()
                        break
                    if step.get("type") == "handoff":
                        await ws.send_json(HandoffPayload(step_id=state.current_step_id).to_dict())
                        call_ended.set()
                        break

            elif event_name == InboundEvent.AUDIO_FRAME and state is not None:
                # Phase 1.1: Feed real audio frame to pipeline
                frame_data = base64.b64decode(raw.get("data", ""))
                if pipeline is not None:
                    pipeline.feed(frame_data)
                    # Phase 1.3 + 5.1: Barge-in from pipeline VAD
                    # speech_active is False during half-duplex suppression window
                    if tts_active and pipeline.is_speech_active:
                        tts_interrupt.set()
                        barge_in_count += 1
                        logger.info("Barge-in #%d (pipeline VAD)", barge_in_count)
                else:
                    # Fallback barge-in when no pipeline (no STT configured)
                    import numpy as np  # noqa: PLC0415
                    from audio.codec import ulaw_to_pcm  # noqa: PLC0415

                    pcm = ulaw_to_pcm(frame_data).astype(np.float32) / 32768.0
                    if tts_active and float(np.sqrt(np.mean(pcm**2))) > 0.01:
                        tts_interrupt.set()
                        barge_in_count += 1

            elif event_name == InboundEvent.UTTERANCE and state is not None:
                # Mock/CI mode: pre-transcribed text bypasses pipeline
                utt = UtteranceMessage.from_dict(raw)
                await transcript_queue.put(utt.text)
                logger.debug("Mock utterance queued: %r", utt.text)

            elif event_name == InboundEvent.QUESTION_ANSWERED and state is not None:
                # Direct WS injection (alternative to Redis)
                msg = QuestionAnsweredMessage.from_dict(raw)
                await answer_queue.put((msg.question_id, msg.answer))

            elif event_name == InboundEvent.HANGUP:
                call_ended.set()
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Unhandled error in call_ws: %s", exc)
        try:
            await ws.send_json({"event": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        call_ended.set()

        # Phase 4: Persist call data
        await _post_call_events()

        # Cancel background tasks
        if pipeline is not None:
            pipeline.stop()
        if pipeline_task is not None:
            pipeline_task.cancel()
        if redis_sub_task is not None:
            redis_sub_task.cancel()
        for t in pending_question_tasks:
            t.cancel()
        turn_task.cancel()
