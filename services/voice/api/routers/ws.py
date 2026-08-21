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
from call.events import (
    CallContext,
    InboundEvent,
    QuestionAnsweredMessage,
    StartMessage,
    UtteranceMessage,
)
from call.media import MediaRouter
from call.session import default_session_manager
from call.turn import TurnOrchestrator
from llm.client import LLMClient
from llm.conversation import ConversationEngine
from llm.nlu import LLMNLUClassifier
from obs import tracing as obs
from runtime.executor import create_session
from telephony import TelephonyAdapter, get_adapter
from tts.chain import TTSChain, build_tts_chain
from tts.fillers import FillerSelector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

_settings = Settings()


async def _fetch_active_script(campaign_id: str) -> dict | None:  # type: ignore[type-arg]
    """Fetch the published script body for a campaign from the Script CMS.

    This is what actually wires the Portal's draft/review/publish/lint/audit
    flow into real calls — without it, publish state is decorative: callers
    would fall back to whatever local JSON file the SIP bridge happens to
    have on disk, bypassing HITL review entirely. Same internal-endpoint
    pattern as nlu/store.py's reload_from_api (no auth, service-to-service).
    """
    url = f"{_settings.api_url}/internal/scripts/{campaign_id}/active"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            version = resp.json()
            return version.get("body")
    except Exception as exc:
        logger.warning("Failed to fetch published script for campaign=%s: %s", campaign_id, exc)
        return None


def _load_script_file(name_or_path: str) -> dict:  # type: ignore[type-arg]
    """Load a script JSON by name from scripts/examples/ or by path.

    Same lookup `simulator/run_sim.py::_find_script` uses — reused here for
    providers with no live orchestrator supplying `script` in their own
    "start" message (e.g. FreeSWITCH: our own Lua bridge script can't
    reasonably embed a full script tree in `uuid_audio_fork`'s single
    command-line-style metadata argument), via the `?script_id=` query param.
    """
    from pathlib import Path  # noqa: PLC0415

    path = Path(name_or_path)
    if not path.exists():
        here = Path(__file__).parent.parent  # services/voice/
        for candidate in (
            here / "../../scripts/examples" / f"{name_or_path}.json",
            here / "../../scripts/examples" / name_or_path,
        ):
            if candidate.exists():
                path = candidate
                break
    with open(path, encoding="utf-8") as f:
        import json  # noqa: PLC0415
        return json.load(f)


async def _iter_wire_frames(ws: WebSocket):
    """Like `WebSocket.iter_json()`, but yields raw `bytes` for binary
    frames instead of choking on them — needed for providers whose audio
    arrives as binary WS frames (mod_audio_fork) rather than base64-in-JSON
    (CloudFone). Text frames are still parsed as JSON, unchanged."""
    import json  # noqa: PLC0415

    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000), message.get("reason"))
            if "bytes" in message and message["bytes"] is not None:
                yield message["bytes"]
            elif "text" in message and message["text"] is not None:
                yield json.loads(message["text"])
    except WebSocketDisconnect:
        pass


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
        "traceId": ctx.trace_id,
        "turnTraces": ctx.turn_traces,
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
async def call_ws(
    ws: WebSocket, script_id: str = "", provider: str = "cloudfone", audio_mode: str = "json"
) -> None:
    """Streaming call WebSocket. Supports real audio (audio_frame) and mock
    (utterance) modes. `provider` selects the telephony adapter — see
    `telephony/`. `audio_mode` (freeswitch only, for now): "json" (default,
    JSON playAudio) or "stream" (raw binary frames, mod_audio_fork's
    bidirectional *streaming* sub-mode — see telephony/freeswitch.py)."""
    await ws.accept()

    adapter: TelephonyAdapter = get_adapter(provider, settings=_settings, audio_mode=audio_mode)
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
    ctx.redis = redis_for_chain

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
            api_key=remote_cfg.ai.api_key,
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
        rag_context_floor=_settings.rag_context_floor,
        on_tts_start=media.on_tts_start, on_tts_end=media.on_tts_end,
    )
    turn_orch = TurnOrchestrator(
        egress, media, dialogue, ctx, active_call,
        nlu=nlu, tts_chain=tts_chain, tts=tts, settings=_settings,
    )

    pipeline_task = None
    redis_sub_task = None
    call_span_cm = None
    turn_task = asyncio.create_task(turn_orch.turn_handler())

    try:
        async for wire_msg in _iter_wire_frames(ws):
            if turn_orch.call_ended.is_set():
                break

            if isinstance(wire_msg, bytes):
                binary_handler = getattr(adapter, "normalize_inbound_binary", None)
                raw = binary_handler(wire_msg) if binary_handler is not None else None
            else:
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
                if not ctx.script and ctx.campaign_id:
                    fetched = await _fetch_active_script(ctx.campaign_id)
                    if fetched:
                        ctx.script = fetched
                if not ctx.script and script_id:
                    try:
                        ctx.script = _load_script_file(script_id)
                    except Exception as exc:
                        logger.error("Failed to load script_id=%s: %s", script_id, exc)
                if ctx.campaign_id and isinstance(ctx.script, dict):
                    # Authoritative campaign_id for NLU/KB scoping — never trust
                    # whatever (possibly stale, possibly wrong-cased) value is
                    # baked into the script body itself. Found via real testing:
                    # runtime/executor.py reads script_body["campaignId"]
                    # (camelCase) but published script bodies carry
                    # "campaign_id" (snake_case) and/or a placeholder UUID —
                    # the mismatch silently returned None, which search_intents/
                    # KB search both treat as "no campaign filter, see everything".
                    ctx.script["campaignId"] = ctx.campaign_id
                ctx.steps = _index_steps(ctx.script)
                ctx.interception_mode = raw.get("interception_mode", "full")
                ctx.interception_domains = raw.get("interception_domains", [])
                ctx.started_at = started_at = time.time()

                # Root span for the whole call. Parented to the traceparent
                # the SIP bridge minted at answer time, so softphone and
                # worker share one trace id rather than opening two traces.
                _tp = raw.get("traceparent", "")
                call_span_cm = obs.span(
                    "call",
                    parent=obs.context_from_traceparent(_tp),
                    **{
                        "session_id": ctx.session_id,
                        "campaign_id": ctx.campaign_id or "",
                        "direction": ctx.caller_direction,
                    },
                )
                _call_span = call_span_cm.__enter__()
                ctx.otel_ctx = obs.context_with_span(_call_span)
                ctx.trace_id = obs.current_trace_id() or (_tp.split("-")[1] if _tp else "")
                _stt_engine = getattr(ws.app.state, "stt", None)
                ctx.stt_engine_name = type(_stt_engine).__name__ if _stt_engine else ""
                ctx.tts_engine_name = (
                    dialogue.tts_chain.primary_engine_name() if dialogue.tts_chain else "beat-only"
                )
                logger.info("Call trace_id=%s session=%s", ctx.trace_id, ctx.session_id)

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
                is_barge_in = media.feed(
                    raw.get("data", ""), tts_active=turn_orch.tts_active or egress.is_playing
                )
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

        # turn_handler() runs as its own task, decoupled from this loop via
        # transcript_queue (so barge-in can interrupt mid-turn) — meaning a
        # HANGUP or disconnect arriving here does not imply the last queued
        # utterance has actually finished processing. If it hasn't (still
        # streaming the farewell TTS, about to set state.status="completed"
        # on landing on a terminal step), _post_call_events below would read
        # a stale state and persist a normally-finished call as "error". A
        # caller hanging up right as the AI's last line starts is the
        # ordinary way this happens, not an edge case. call_ended is already
        # set, so turn_handler's own while-loop will exit right after it
        # finishes whatever it's mid-flight on — just give it a bounded
        # window to get there before we read `state`.
        try:
            await asyncio.wait_for(turn_task, timeout=10.0)
        except (TimeoutError, asyncio.CancelledError):
            logger.warning(
                "turn_handler did not settle within 10s of call end, session=%s — "
                "posting call-events with whatever state is current",
                ctx.session_id,
            )
        except Exception:
            logger.exception("turn_handler task raised while draining on call end")

        await _post_call_events(ctx, turn_orch, started_at)

        # Close the call root span so Tempo gets a complete trace. Must run
        # after _post_call_events so the persisted trace id matches the span
        # that actually gets exported.
        if call_span_cm is not None:
            try:
                call_span_cm.__exit__(None, None, None)
            except Exception:
                logger.debug("call span close failed", exc_info=True)

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


@router.websocket("/watch/{phone}")
async def watch_call_ws(ws: WebSocket, phone: str) -> None:
    """Live-watch a real voip24h call by caller number — Portal Simulator's
    "gọi số thật" feature. Subscribes to the Redis channel call/turn.py
    publishes to (call:live:{phone}) and relays every message verbatim to
    whoever's watching. No session_id needed upfront since the dial
    request only knows the phone number, not the session the SIP bridge
    will mint once the call is answered.
    """
    await ws.accept()
    try:
        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[type-arg]
            _settings.redis_url, decode_responses=True
        )
    except Exception as exc:
        logger.warning("watch_call_ws: Redis unavailable: %s", exc)
        await ws.close(code=1011)
        return

    pubsub = redis_client.pubsub()
    channel = f"call:live:{phone}"
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                await ws.send_text(message["data"])
            except Exception:
                break
    except Exception:
        logger.debug("watch_call_ws: listener ended", exc_info=True)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
        try:
            await redis_client.close()
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
