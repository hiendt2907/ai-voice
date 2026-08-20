"""Thin WS transport shim for `/ws/call`.

Accepts the WebSocket, resolves the telephony adapter, builds the per-call
`call/` core (SessionManager admission, MediaRouter, EgressSender,
DialogueEngine, TurnOrchestrator), and forwards inbound wire events to it.
All call business logic (session, media, turn, dialogue, egress) lives in
`call/` — see `docs/ai-streaming-voice-architecture-proposal.md` section G
(Phase 1) for the extraction rationale.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.config import Settings
from call.dialogue import DialogueEngine
from call.egress import EgressSender
from call.events import CallContext, InboundEvent, QuestionAnsweredMessage, StartMessage, UtteranceMessage
from call.media import MediaRouter
from call.session import default_session_manager
from call.turn import TurnOrchestrator
from llm.client import LLMClient
from llm.conversation import ConversationEngine
from llm.nlu import LLMNLUClassifier
from runtime.executor import create_session
from telephony import TelephonyAdapter, get_adapter
from tts.chain import TTSChain, build_tts_chain
from tts.fillers import FillerSelector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

_settings = Settings()


@router.get("/tts-health")
async def tts_health() -> dict:
    """TTS engine circuit breaker + quota status."""
    from api.remote_config import RemoteConfig  # noqa: PLC0415

    try:
        cfg = await RemoteConfig(_settings).load()
        r = await aioredis.from_url(_settings.redis_url, decode_responses=False)
        chain = build_tts_chain(cfg.tts, r)
        quota_status = await chain._quota.status()
        return {"engines": chain.engine_status(), "quota": quota_status}
    except Exception as exc:
        return {"error": str(exc)}


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


def _index_steps(script: dict) -> dict[str, dict]:
    return {s["id"]: s for s in script.get("steps", [])}


async def _post_call_events(ctx: CallContext, turn_orch: TurnOrchestrator, started_at: float) -> None:
    """Phase 4: persist call data to NestJS on hangup."""
    state = turn_orch.state
    if state is None:
        return
    transcript_dicts = [
        {"step_id": e.step_id, "role": e.role, "text": e.text, "intent": e.intent}
        for e in state.transcript
    ]
    payload: dict[str, Any] = {
        "sessionId": state.session_id,
        "campaignId": ctx.campaign_id,
        "scriptVersionId": ctx.script_version_id,
        "direction": ctx.caller_direction,
        "callerNumber": ctx.caller_number,
        "status": state.status if state.status in ("completed", "handoff") else "error",
        "transcript": transcript_dicts,
        "slots": dict(state.slots),
        "finalStepId": state.current_step_id,
        "durationSeconds": round(time.time() - started_at),
        "startedAt": datetime.fromtimestamp(started_at).isoformat(),
        "endedAt": datetime.now().isoformat(),
        "meta": {
            "bargeInCount": ctx.barge_in_count,
            "noMatchCounts": dict(state.no_match_counts),
            "lastRagScore": ctx.last_rag_score,
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


@router.websocket("/call")
async def call_ws(ws: WebSocket, script_id: str = "", provider: str = "cloudfone") -> None:
    """Streaming call WebSocket. Supports real audio (audio_frame) and mock
    (utterance) modes. `provider` selects the telephony adapter — see
    `telephony/`."""
    await ws.accept()

    adapter: TelephonyAdapter = get_adapter(provider, settings=_settings)
    egress = EgressSender(ws, adapter)
    ctx = CallContext()
    started_at = time.time()
    active_call = None

    from api.remote_config import RemoteConfig  # noqa: PLC0415
    remote_cfg = await RemoteConfig(_settings).load()

    try:
        redis_for_chain: aioredis.Redis = aioredis.from_url(  # type: ignore[type-arg]
            _settings.redis_url, decode_responses=False
        )
    except Exception:
        redis_for_chain = None  # type: ignore[assignment]

    tts_chain: TTSChain | None = None
    if _settings.use_real_tts and redis_for_chain is not None:
        try:
            tts_chain = build_tts_chain(remote_cfg.tts, redis_for_chain)
        except Exception as exc:
            logger.warning("Failed to build TTSChain: %s — beat mode", exc)

    try:
        tts = ws.app.state.tts  # prefer app.state.tts (has redis for metrics)
    except AttributeError:
        tts = None

    conv_engine: ConversationEngine | None = None
    if remote_cfg.conversation.enabled:
        conv_engine = ConversationEngine(
            ollama_base_url=remote_cfg.ai.ollama_base_url,
            model=remote_cfg.conversation.ollama_model,
            system_prompt=remote_cfg.conversation.system_prompt,
            temperature=remote_cfg.conversation.temperature,
            max_history_turns=remote_cfg.conversation.max_history_turns,
        )
        logger.info(
            "ConversationEngine enabled (model=%s, sentiment=%s)",
            remote_cfg.conversation.ollama_model, remote_cfg.conversation.sentiment_enabled,
        )

    nlu = _build_nlu()
    media = MediaRouter(
        session_id="", egress=egress, use_silero_vad=_settings.use_silero_vad
    )  # session_id filled in on START
    dialogue = DialogueEngine(
        egress, ctx,
        conv_engine=conv_engine, tts_chain=tts_chain, tts=tts,
        filler_selector=FillerSelector(),
        kb_grounding_enabled=remote_cfg.conversation.kb_grounding_enabled,
        max_history_turns=remote_cfg.conversation.max_history_turns,
        sentence_split_min_chars=remote_cfg.conversation.sentence_split_min_chars,
        rag_confidence_default=_settings.rag_confidence_default,
        on_tts_start=media.on_tts_start, on_tts_end=media.on_tts_end,
    )
    turn_orch = TurnOrchestrator(
        egress, media, dialogue, ctx, active_call,
        nlu=nlu, tts_chain=tts_chain, tts=tts, settings=_settings,
    )

    pipeline_task = None
    redis_sub_task = None
    turn_task = asyncio.create_task(turn_orch.turn_handler())

    try:
        async for wire_msg in ws.iter_json():
            if turn_orch.call_ended.is_set():
                break

            raw = adapter.normalize_inbound(wire_msg)
            if raw is None:
                continue  # provider message with no internal-event equivalent

            event_name: str = raw.get("event", "")

            if event_name == InboundEvent.START:
                client_wants_tts = raw.get("use_real_tts")
                if client_wants_tts is True and dialogue.tts_chain is None and redis_for_chain is not None:
                    try:
                        dialogue.tts_chain = build_tts_chain(remote_cfg.tts, redis_for_chain)
                        turn_orch.tts_chain = dialogue.tts_chain
                        turn_orch.handoff.tts_chain = dialogue.tts_chain
                        logger.info("Per-connection TTS override: built TTSChain %s", dialogue.tts_chain.engine_status())
                    except Exception as exc:
                        logger.warning("Per-connection TTS build failed: %s", exc)
                elif client_wants_tts is False:
                    dialogue.tts_chain = None
                    turn_orch.tts_chain = None
                    turn_orch.handoff.tts_chain = None
                    logger.info("Per-connection TTS disabled by client (beat mode)")

                logger.info("START: campaign=%s tts=%s", raw.get("campaign_id"), type(tts).__name__ if tts else "mock(beat)")
                start = StartMessage.from_dict(raw)
                ctx.session_id = start.session_id or str(uuid.uuid4())
                ctx.campaign_id = start.campaign_id
                ctx.script_version_id = start.script_version_id
                ctx.caller_number = start.caller_number
                ctx.caller_direction = start.direction
                ctx.script = raw.get("script", {})
                ctx.steps = _index_steps(ctx.script)
                ctx.interception_mode = raw.get("interception_mode", "full")
                ctx.interception_domains = raw.get("interception_domains", [])
                ctx.started_at = started_at = time.time()

                media.session_id = ctx.session_id
                active_call = default_session_manager.register(ctx.session_id)
                turn_orch.active_call = active_call
                turn_orch.start_session(create_session(ctx.script))

                try:
                    stt = ws.app.state.stt
                except AttributeError:
                    stt = None  # tests may not have app.state

                pipeline_task = media.start(
                    stt, turn_orch.on_transcript, turn_orch.speak_fallback_and_end_call,
                    turn_id_provider=lambda: str(turn_orch.turn + 1),
                )
                redis_sub_task = turn_orch.start_redis_answer_subscriber(_settings.redis_url)

                ended = await turn_orch.greet()
                if ended:
                    break

            elif event_name == InboundEvent.AUDIO_FRAME and turn_orch.state is not None:
                # `turn_orch.tts_active` alone flips False as soon as the
                # server finishes SYNTHESIZING a turn's audio — but fast
                # engines (Piper) can push several seconds of audio over the
                # WS in a few hundred ms, so the client is still audibly
                # PLAYING it well after that. `egress.is_playing` is the
                # audio-position clock that covers that tail (see
                # call/egress.py); either signal makes barge-in eligible.
                _gate = turn_orch.tts_active or egress.is_playing
                if _gate:
                    logger.info(
                        "DEBUG_GATE tts_active=%s is_playing=%s deadline_remaining_ms=%.1f",
                        turn_orch.tts_active, egress.is_playing,
                        (egress._playback_deadline - time.monotonic()) * 1000,
                    )
                is_barge_in = media.feed(raw.get("data", ""), tts_active=_gate)
                if is_barge_in:
                    logger.info("DEBUG_BARGEIN_DETECTED turn=%s", turn_orch.turn)
                # Only act once per interruption, not once per audio frame
                # (an interruption spans many frames while the caller keeps
                # talking) — `tts_interrupt` being unset is exactly "this is
                # the first frame of a new barge-in" since it's cleared at
                # the start of every turn (fixes D7's inflated counter as a
                # side effect of not spamming `flush` every frame too).
                if is_barge_in and not turn_orch.tts_interrupt.is_set():
                    turn_orch.tts_interrupt.set()
                    ctx.barge_in_count += 1
                    logger.info("Barge-in #%d", ctx.barge_in_count)
                    await media.flush(turn_orch.turn)

            elif event_name == InboundEvent.UTTERANCE and turn_orch.state is not None:
                # Mock/CI mode: pre-transcribed text bypasses the pipeline.
                utt = UtteranceMessage.from_dict(raw)
                await turn_orch.on_transcript(utt.text, utt.emotion)
                logger.debug("Mock utterance queued: %r (emotion=%s)", utt.text, utt.emotion)

            elif event_name == InboundEvent.QUESTION_ANSWERED and turn_orch.state is not None:
                msg = QuestionAnsweredMessage.from_dict(raw)
                await turn_orch.on_answer(msg.question_id, msg.answer)

            elif event_name == InboundEvent.HANGUP:
                turn_orch.call_ended.set()
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Unhandled error in call_ws: %s", exc)
        try:
            await egress.send({"event": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        turn_orch.call_ended.set()

        await _post_call_events(ctx, turn_orch, started_at)

        media.stop()
        if pipeline_task is not None:
            pipeline_task.cancel()
        if redis_sub_task is not None:
            redis_sub_task.cancel()
        for t in turn_orch.pending_question_tasks:
            t.cancel()
        turn_task.cancel()
        if active_call is not None:
            default_session_manager.unregister(ctx.session_id)

        # Round 4 finding: every call-end path here (HANGUP break, HITL/NLU
        # handoff via turn_orch, or falling out of the loop for any other
        # reason) previously just returned from this handler without ever
        # sending a WS close frame. Starlette doesn't do this implicitly, so
        # uvicorn tears down the raw TCP connection instead of performing a
        # clean WS close handshake — clients see an abrupt
        # `ConnectionClosedError` ("no close frame received or sent") even
        # though the call actually completed normally server-side. Close
        # explicitly so well-behaved clients can tell a normal end-of-call
        # apart from a real fault. Best-effort: the socket may already be
        # gone (e.g. WebSocketDisconnect path), so swallow errors here.
        try:
            await ws.close()
        except Exception:
            pass
