"""SessionManager — active-call registry + admission control.

Phase 1 scope: track which calls are currently active on this process so we
can *count* concurrent calls. Enforcing a hard cap (benchmark M4=2) and
Redis-backed cross-process state are explicitly deferred — see the
"Chưa làm" list in the Phase 1 handoff report. This module only needs to be
structurally correct now; Phase 2 wires in real admission control once
there's a load benchmark to enforce against.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ActiveCall:
    session_id: str
    started_at: float = field(default_factory=time.time)


class SessionManager:
    """Process-local registry of in-flight calls.

    One instance is shared across all `/ws/call` connections handled by this
    worker process (see `default_session_manager` below, or wire an instance
    into `app.state.session_manager` in `api/main.py` for testability).
    """

    def __init__(self) -> None:
        self._active: dict[str, ActiveCall] = {}

    def register(self, session_id: str) -> ActiveCall:
        call = ActiveCall(session_id=session_id)
        self._active[session_id] = call
        logger.info("SessionManager: register session_id=%s active=%d", session_id, self.count)
        return call

    def unregister(self, session_id: str) -> None:
        self._active.pop(session_id, None)
        logger.info("SessionManager: unregister session_id=%s active=%d", session_id, self.count)

    @property
    def count(self) -> int:
        return len(self._active)

    def is_active(self, session_id: str) -> bool:
        return session_id in self._active

    # TODO(Phase 2): enforce a hard admission cap once M4 benchmark exists.
    # def admit(self, cap: int = 2) -> bool:
    #     return self.count < cap


default_session_manager = SessionManager()
