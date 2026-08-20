"""OpenTelemetry setup — exports spans to Tempo over OTLP/HTTP.

Tracing is optional: if the SDK isn't installed or the collector is
unreachable, every helper here degrades to a no-op rather than taking the
call down with it. Observability must never be the reason a call fails.

Span shape for one call:

    call {session_id, campaign_id, caller_number_masked}
    └── turn {n}
        ├── stt   {text, confidence, engine}
        ├── nlu   {tier, intent, confidence, llm_used}
        ├── rag   {hit, article_id, score}
        ├── llm   {model, prompt_tokens, completion_tokens}
        └── tts   {engine, ttfa_ms, chars}
"""

from __future__ import annotations

import contextlib
import logging
import os
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_tracer: Any = None
_enabled = False


def init_tracing(service_name: str = "voice-worker") -> bool:
    """Wire up the OTLP exporter. Returns True when tracing is live.

    Endpoint comes from OTEL_EXPORTER_OTLP_ENDPOINT; unset means tracing off,
    so local runs and tests stay clean without extra configuration.
    """
    global _tracer, _enabled

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.info("Tracing disabled (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        return False

    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

        provider = TracerProvider(
            resource=Resource.create({
                "service.name": service_name,
                "service.namespace": "ai-voice",
                "deployment.environment": os.getenv("DEPLOY_ENV", "gcp"),
            })
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        _enabled = True
        logger.info("Tracing enabled → %s", endpoint)
        return True
    except Exception as exc:  # noqa: BLE001 — never fail startup over telemetry
        logger.warning("Tracing setup failed (continuing without it): %s", exc)
        return False


def is_enabled() -> bool:
    return _enabled


def new_traceparent() -> str:
    """Mint a W3C traceparent for a call that is starting.

    Called by the SIP bridge the moment a call is answered, so the trace id
    covers the call from its real beginning and every hop — softphone,
    voice worker, NestJS, the row in Postgres — carries the same id. Works
    without the OTel SDK: this is just the wire format.
    """
    import secrets  # noqa: PLC0415

    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def context_from_traceparent(traceparent: str) -> Any:
    """Turn an inbound traceparent header into an OTel context to parent a
    span under, so the worker's spans join the caller's trace instead of
    starting a second one."""
    if not _enabled or not traceparent:
        return None
    try:
        from opentelemetry.propagate import extract  # noqa: PLC0415

        return extract({"traceparent": traceparent})
    except Exception:  # noqa: BLE001
        return None


@contextmanager
def span(name: str, parent: Any = None, **attributes: Any):
    """Start a span, or do nothing when tracing is off.

    Yields the span so callers can add attributes discovered mid-work (an
    intent isn't known until the classifier returns). The yielded object is
    None when disabled — call `set_attr` rather than touching it directly.
    """
    if not _enabled or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name, context=parent) as sp:
        for key, value in attributes.items():
            if value is not None:
                sp.set_attribute(key, value)
        yield sp


def set_attr(sp: Any, key: str, value: Any) -> None:
    """Attribute setter that tolerates a disabled tracer (sp is None)."""
    if sp is not None and value is not None:
        # Telemetry must never raise into call logic.
        with contextlib.suppress(Exception):
            sp.set_attribute(key, value)


def current_span() -> Any:
    """Active span, or None when tracing is off."""
    if not _enabled:
        return None
    try:
        from opentelemetry import trace  # noqa: PLC0415

        return trace.get_current_span()
    except Exception:  # noqa: BLE001
        return None


def current_trace_id() -> str:
    """Hex trace id of the active span, or "" — this is what links a call
    record in Postgres to its trace in Grafana/Tempo."""
    if not _enabled:
        return ""
    try:
        from opentelemetry import trace  # noqa: PLC0415

        ctx = trace.get_current_span().get_span_context()
        if not ctx.is_valid:
            return ""
        return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001
        return ""
