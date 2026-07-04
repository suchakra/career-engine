"""Regression: the checkpoint confirm loop resolves over the DURABLE (Firestore) path.

A user reported the web checkpoint re-appearing after 'Looks right — keep going'.
The graph resolution + flag persistence were suspected. This proves the exact web
path — `DiscoverySession.confirm_checkpoint()` (patch checkpoint_verified=True →
run a turn) — advances CHECKPOINT → GRILLING and clears the checkpoint under BOTH
InMemorySessionService and FirestoreSessionService (the append_event override
persists each turn), i.e. identically to the in-memory service.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from google.adk.sessions import BaseSessionService, InMemorySessionService

import workflows.nodes as nodes
from cli import session as session_helpers
from cli.app import DiscoverySession
from config import AccessMode
from database.firestore_session import FirestoreSessionService
from integration.model_client import GeminiModelClient
from schema import CareerEngineState, Entry, EntryStatus, PhaseStatus
from tests.fakes import FakeFirestoreClient
from tests.test_integration import ScriptedNodeClient

_APP, _UID, _SID = "career-engine", "u", "web-u"


@pytest.fixture(autouse=True)
def _restore_model_client_factory() -> Iterator[None]:
    """Restore the global node model-client factory so this test doesn't leak into others."""
    original = nodes._client_factory
    yield
    nodes._client_factory = original


def _services() -> list[BaseSessionService]:
    return [
        cast(BaseSessionService, InMemorySessionService()),  # type: ignore[no-untyped-call]
        FirestoreSessionService(client=FakeFirestoreClient()),
    ]


@pytest.mark.parametrize("svc", _services(), ids=["in_memory", "firestore"])
async def test_confirm_checkpoint_advances_to_grilling(svc: BaseSessionService) -> None:
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
    # DiscoverySession installs this client into the workflow nodes itself (via
    # _install_model_client), so a scripted node client is all we need here.
    client = ScriptedNodeClient(responses={"summarizing progress": "Recap. Accurate?"})
    session = DiscoverySession(
        user_id=_UID,
        access_mode=AccessMode.BYOK,
        model_client=cast(GeminiModelClient, client),
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
