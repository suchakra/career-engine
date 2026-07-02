"""Tests for web/session_loader.py — the discovery-state loader for the meter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from google.adk.sessions import BaseSessionService

from schema import CareerEngineState
from web.session_loader import (
    load_latest_discovery_state,
    try_load_latest_discovery_state,
)

_APP = "career-engine"
_UID = "user-1"


def _session(sid: str, *, updated: float, state: dict[str, Any] | None) -> SimpleNamespace:
    return SimpleNamespace(id=sid, last_update_time=updated, state=state)


class _FakeSessionService:
    """Duck-typed session service: list_sessions (lightweight) + get_session (full)."""

    def __init__(self, sessions: list[SimpleNamespace]) -> None:
        self._sessions = sessions

    async def list_sessions(self, *, app_name: str, user_id: str) -> SimpleNamespace:
        # list is lightweight: id + last_update_time only (no state).
        return SimpleNamespace(
            sessions=[_session(s.id, updated=s.last_update_time, state=None) for s in self._sessions]
        )

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str, config: Any = None
    ) -> SimpleNamespace | None:
        return next((s for s in self._sessions if s.id == session_id), None)


class _RaisingSessionService:
    async def list_sessions(self, *, app_name: str, user_id: str) -> SimpleNamespace:
        raise RuntimeError("backend unreachable")

    async def get_session(self, **_: Any) -> SimpleNamespace | None:  # pragma: no cover
        raise RuntimeError("backend unreachable")


def _svc(obj: object) -> BaseSessionService:
    return cast(BaseSessionService, obj)


class TestLoadLatestDiscoveryState:
    def test_picks_most_recent_session_state(self) -> None:
        older = CareerEngineState(reference_date="2026-06-01", question_count=1).model_dump(mode="json")
        newer = CareerEngineState(reference_date="2026-07-01", question_count=4).model_dump(mode="json")
        svc = _FakeSessionService(
            [
                _session("old", updated=100.0, state=older),
                _session("new", updated=200.0, state=newer),
            ]
        )
        state = load_latest_discovery_state(
            _svc(svc), app_name=_APP, user_id=_UID, reference_date="2026-07-02"
        )
        assert state.question_count == 4  # the newer session won

    def test_no_sessions_returns_empty_state(self) -> None:
        state = load_latest_discovery_state(
            _svc(_FakeSessionService([])), app_name=_APP, user_id=_UID, reference_date="2026-07-02"
        )
        assert state.question_count == 0
        assert state.reference_date == "2026-07-02"

    def test_session_without_state_returns_empty(self) -> None:
        svc = _FakeSessionService([_session("s", updated=1.0, state=None)])
        state = load_latest_discovery_state(
            _svc(svc), app_name=_APP, user_id=_UID, reference_date="2026-07-02"
        )
        assert state.question_count == 0


class TestTryLoadLatestDiscoveryState:
    def test_backend_failure_returns_empty_state(self) -> None:
        state = try_load_latest_discovery_state(
            _svc(_RaisingSessionService()),
            app_name=_APP,
            user_id=_UID,
            reference_date="2026-07-02",
        )
        assert isinstance(state, CareerEngineState)
        assert state.question_count == 0
        assert state.reference_date == "2026-07-02"

    def test_success_path_delegates(self) -> None:
        good = CareerEngineState(reference_date="2026-07-01", question_count=2).model_dump(mode="json")
        svc = _FakeSessionService([_session("s", updated=1.0, state=good)])
        state = try_load_latest_discovery_state(
            _svc(svc), app_name=_APP, user_id=_UID, reference_date="2026-07-02"
        )
        assert state.question_count == 2
