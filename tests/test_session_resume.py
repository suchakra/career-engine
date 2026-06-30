"""Tests for true session-resume semantics (Phase 1.7-B).

Verifies the load-before-create primitive: an existing persisted session is
loaded (not clobbered), a missing session returns None (so a fresh session can
start cleanly), and prior grill progress / frontier continuity survives.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest
from google.adk.sessions import BaseSessionService, InMemorySessionService

import cli.app as app
from cli.session import create_session, get_session_state_if_exists
from config import AccessMode
from integration.model_client import GeminiModelClient
from schema import (
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    PhaseStatus,
)

APP = "career_engine_discovery"
USER = "user-1"


def _svc() -> BaseSessionService:
    """Return a fresh in-memory session service."""
    return cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]


def _progress_state() -> CareerEngineState:
    """A state mid-discovery: one grilled entry, one pending, frontier + count set."""
    grilled = Entry(
        type=ExperienceType.FULL_TIME,
        title="Recent Role",
        start_date="2023",
        end_date="2024",
        status=EntryStatus.GRILLED,
    )
    pending = Entry(
        type=ExperienceType.FULL_TIME,
        title="Older Role",
        start_date="2019",
        end_date="2021",
        status=EntryStatus.NEEDS_QUANTIFYING,
    )
    return CareerEngineState(
        current_phase=PhaseStatus.GRILLING,
        work_timeline=[grilled, pending],
        grill_frontier=str(pending.entry_id),
        question_count=3,
        reference_date="2026-06-30",
    )


class TestSessionResume:
    """get_session_state_if_exists loads existing sessions without clobbering."""

    async def test_existing_session_is_loaded_not_clobbered(self) -> None:
        """A persisted session round-trips with its progress intact."""
        svc = _svc()
        state = _progress_state()
        await create_session(
            session_service=svc,
            app_name=APP,
            user_id=USER,
            session_id="s-resume",
            initial_state=state,
        )

        loaded = await get_session_state_if_exists(
            session_service=svc, app_name=APP, user_id=USER, session_id="s-resume"
        )

        assert loaded is not None
        # Prior progress survives — not reset to a fresh INGESTING state.
        assert loaded.current_phase == PhaseStatus.GRILLING
        assert loaded.question_count == 3
        assert loaded.grill_frontier == state.grill_frontier
        statuses = {e.title: e.status for e in loaded.work_timeline}
        assert statuses["Recent Role"] == EntryStatus.GRILLED
        assert statuses["Older Role"] == EntryStatus.NEEDS_QUANTIFYING

    async def test_missing_session_returns_none(self) -> None:
        """A never-created session id returns None (no error, no stack leak)."""
        svc = _svc()
        loaded = await get_session_state_if_exists(
            session_service=svc, app_name=APP, user_id=USER, session_id="does-not-exist"
        )
        assert loaded is None

    async def test_new_session_starts_clean_after_create(self) -> None:
        """A freshly created INGESTING session loads back as INGESTING."""
        svc = _svc()
        await create_session(
            session_service=svc,
            app_name=APP,
            user_id=USER,
            session_id="s-new",
            initial_state=CareerEngineState(raw_history_text="hi"),
        )
        loaded = await get_session_state_if_exists(
            session_service=svc, app_name=APP, user_id=USER, session_id="s-new"
        )
        assert loaded is not None
        assert loaded.current_phase == PhaseStatus.INGESTING
        assert loaded.work_timeline == []


@pytest.fixture
def _restore_nodes_client() -> object:
    """Restore the global node client factory after a test installs one."""
    import workflows.nodes as nodes

    original = nodes._client_factory
    yield None
    nodes._client_factory = original


class TestResumeCliErrorPath:
    """run_interactive_session surfaces a user-safe error for a missing session."""

    def test_missing_session_id_prints_safe_message_no_raise(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        _restore_nodes_client: object,
    ) -> None:
        """--session-id with no persisted state prints guidance and returns cleanly."""
        monkeypatch.setattr(
            app,
            "resolve_auth_and_client",
            lambda: ("u", AccessMode.FREE, cast(GeminiModelClient, MagicMock())),
        )
        # Default (in-memory) service is fresh → the session id does not exist.
        app.run_interactive_session(raw_history="x", session_id="no-such-id")
        err = capsys.readouterr().err
        assert "No saved session" in err
        assert "no-such-id" in err
