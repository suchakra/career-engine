"""Regression: the checkpoint confirm loop resolves over the DURABLE (Firestore) path.

A user reported the web checkpoint re-appearing after 'Looks right — keep going'.
The graph resolution + flag persistence were suspected. This proves the exact web
path — `DiscoverySession.confirm_checkpoint()` (patch checkpoint_verified=True →
run a turn) — advances CHECKPOINT → GRILLING and clears the checkpoint when backed
by `FirestoreSessionService` (the append_event override persists each turn), i.e.
identically to the in-memory service.
"""

from __future__ import annotations

from typing import cast

import pytest
from google.adk.sessions import BaseSessionService, InMemorySessionService

from cli import session as session_helpers
from cli.app import DiscoverySession
from config import AccessMode
from database.firestore_session import FirestoreSessionService
from integration.model_client import GeminiModelClient
from schema import CareerEngineState, Entry, EntryStatus, PhaseStatus
from tests.fakes import FakeFirestoreClient
from tests.test_integration import ScriptedNodeClient
from workflows.nodes import set_model_client_factory

_APP, _UID, _SID = "career-engine", "u", "web-u"


def _services() -> list[BaseSessionService]:
    return [
        cast(BaseSessionService, InMemorySessionService()),  # type: ignore[no-untyped-call]
        FirestoreSessionService(client=FakeFirestoreClient()),
    ]


@pytest.mark.parametrize("svc", _services(), ids=["in_memory", "firestore"])
async def test_confirm_checkpoint_advances_to_grilling(svc: BaseSessionService) -> None:
    set_model_client_factory(
        lambda: ScriptedNodeClient(responses={"summarizing progress": "Recap. Accurate?"})
    )
    pending = Entry(
        title="Leadership Role", start_date="2021", status=EntryStatus.NEEDS_QUANTIFYING
    )
    await session_helpers.create_session(
        session_service=svc,
        app_name=_APP,
        user_id=_UID,
        session_id=_SID,
        initial_state=CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            work_timeline=[pending],
            grill_frontier=str(pending.entry_id),
            checkpoint_delta_summary="Recap. Accurate?",
            checkpoint_verified=False,  # awaiting confirmation, as the UI leaves it
            question_count=5,
        ),
    )
    session = DiscoverySession(
        user_id=_UID,
        access_mode=AccessMode.BYOK,
        # The node model client is installed via the factory above; DiscoverySession
        # only needs an object satisfying the type here (duck-typed in the graph).
        model_client=cast(GeminiModelClient, ScriptedNodeClient(responses={})),
        session_service=svc,
        app_name=_APP,
        session_id=_SID,
    )

    await session.confirm_checkpoint()  # patch checkpoint_verified=True → run a turn

    state = await session.current_state()
    assert state.current_phase == PhaseStatus.GRILLING  # advanced, did NOT re-checkpoint
    assert state.checkpoint_verified is False  # flag reset
    assert state.checkpoint_delta_summary == ""  # summary cleared
    assert state.question_count > 5  # counter stepped off the 5-multiple (no re-brake)
