"""Tests for the portfolio-mutation seam (Phase 4D/4C).

Uses ADK's real ``InMemorySessionService`` so the state_delta merge semantics
match production (the seam commits via an appended Event, like the workflow's own
nodes). Covers: add-to-existing, add-when-none (creates a session), contract
stamping, title validation, and the grill_frontier jump (incl. the no-session case).
"""

from __future__ import annotations

import asyncio
from typing import cast

from google.adk.sessions import BaseSessionService, InMemorySessionService

from config import CONTRACT_VERSION
from schema import CareerEngineState, Entry, ExperienceType
from web.portfolio_store import add_manual_entry, set_grill_frontier

_APP = "career-engine"
_UID = "user-1"
_REF = "2026-07-04"


def _service() -> BaseSessionService:
    return cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]


def _seed(service: BaseSessionService, state: CareerEngineState, *, sid: str = "s1") -> None:
    asyncio.run(
        service.create_session(
            app_name=_APP, user_id=_UID, session_id=sid, state=state.model_dump(mode="json")
        )
    )


def _read_latest(service: BaseSessionService) -> CareerEngineState:
    async def _go() -> CareerEngineState:
        response = await service.list_sessions(app_name=_APP, user_id=_UID)
        sessions = list(getattr(response, "sessions", []) or [])
        latest = max(sessions, key=lambda s: s.last_update_time or 0.0)
        full = await service.get_session(app_name=_APP, user_id=_UID, session_id=latest.id)
        assert full is not None
        return CareerEngineState.model_validate(full.state)

    return asyncio.run(_go())


class TestAddManualEntry:
    def test_appends_to_existing_session(self) -> None:
        service = _service()
        existing = Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme")
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[existing]))

        add_manual_entry(
            service,
            app_name=_APP,
            user_id=_UID,
            reference_date=_REF,
            title="Billing rewrite",
            org="Acme",
            experience_type=ExperienceType.PROJECT,
        )

        state = _read_latest(service)
        assert [e.title for e in state.work_timeline] == ["Staff Engineer", "Billing rewrite"]
        added = state.work_timeline[-1]
        assert added.source == "manual"
        assert added.type == ExperienceType.PROJECT

    def test_creates_session_when_none_exists(self) -> None:
        service = _service()
        sid = add_manual_entry(
            service,
            app_name=_APP,
            user_id=_UID,
            reference_date=_REF,
            title="Open-source parser",
            experience_type=ExperienceType.OPEN_SOURCE,
        )
        assert sid
        state = _read_latest(service)
        assert len(state.work_timeline) == 1
        assert state.work_timeline[0].title == "Open-source parser"
        assert state.work_timeline[0].source == "manual"

    def test_saved_state_is_contract_stamped(self) -> None:
        service = _service()
        _seed(service, CareerEngineState(reference_date=_REF))
        add_manual_entry(
            service, app_name=_APP, user_id=_UID, reference_date=_REF, title="Thing"
        )
        assert _read_latest(service).contract_version == CONTRACT_VERSION

    def test_bullets_are_cleaned(self) -> None:
        service = _service()
        add_manual_entry(
            service,
            app_name=_APP,
            user_id=_UID,
            reference_date=_REF,
            title="Thing",
            bullets=["Did X", "  ", "Did Y"],
        )
        assert _read_latest(service).work_timeline[0].bullets == ["Did X", "Did Y"]

    def test_empty_title_rejected(self) -> None:
        service = _service()
        try:
            add_manual_entry(
                service, app_name=_APP, user_id=_UID, reference_date=_REF, title="   "
            )
        except ValueError:
            return
        raise AssertionError("empty title should raise ValueError")


class TestSetGrillFrontier:
    def test_pins_frontier_on_latest_session(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing rewrite")
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = set_grill_frontier(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id)
        )
        assert sid is not None
        assert _read_latest(service).grill_frontier == str(entry.entry_id)

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        result = set_grill_frontier(
            service, app_name=_APP, user_id=_UID, entry_id="whatever"
        )
        assert result is None
