"""Unit tests for call.session.SessionManager (admission-control registry)."""

from __future__ import annotations

from call.session import SessionManager


def test_register_adds_active_call():
    mgr = SessionManager()
    call = mgr.register("session-1")

    assert call.session_id == "session-1"
    assert mgr.count == 1
    assert mgr.is_active("session-1") is True


def test_unregister_removes_active_call():
    mgr = SessionManager()
    mgr.register("session-1")

    mgr.unregister("session-1")

    assert mgr.count == 0
    assert mgr.is_active("session-1") is False


def test_unregister_unknown_session_is_a_noop():
    mgr = SessionManager()

    mgr.unregister("never-registered")  # must not raise

    assert mgr.count == 0


def test_count_tracks_multiple_concurrent_calls():
    mgr = SessionManager()
    mgr.register("a")
    mgr.register("b")
    mgr.register("c")

    assert mgr.count == 3

    mgr.unregister("b")

    assert mgr.count == 2
    assert mgr.is_active("a") is True
    assert mgr.is_active("b") is False
    assert mgr.is_active("c") is True
