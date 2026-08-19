"""`call/` — the extracted call core (Phase 1 of the streaming-voice refactor).

See docs/ai-streaming-voice-architecture-proposal.md, section G, for the
rationale: `api/routers/ws.py` used to contain the entire real-time call
pipeline (session mgmt, audio, turn handling, dialogue, TTS egress) in one
1000+ line closure. This package splits that into focused, independently
testable collaborators. `api/routers/ws.py` is now a thin WS transport shim
that wires these together per-connection.

FSM logic (`runtime/fsm.py`, `runtime/executor.py`, `runtime/intent_matcher.py`)
is NOT touched or moved here — `call.turn.TurnOrchestrator` calls into it
exactly as `ws.py` used to, behind the script's `execution_mode` flag.
"""
