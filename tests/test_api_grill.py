"""Tests for the streaming grill API (api/routes_grill.py, api/schemas.py — Phase 10.4).

Network-free: a real :class:`DiscoverySession` is built over ``InMemorySessionService``
+ a :class:`ScriptedNodeClient` (so the discovery graph runs deterministically with no
model network), and injected wholesale via ``app.dependency_overrides`` for
``api.deps.get_discovery_session`` — so the BYOK vault + ``GeminiModelClient`` are never
touched. Auth is a fake, network-free verifier (copied from ``tests/test_api_write.py``).

Acceptance criteria verified (Phase 10.4, AD-16.5):
- ``POST /api/grill`` RECORDS input (no graph run); ``GET /api/grill/stream`` RUNS the
  pending turn sequence over SSE, one ``event: turn`` per completed turn + ``event: done``.
- The auto-advance loop mirrors ``web/grill_ui._submit_answer`` (advance only after a
  story is accepted; single follow-up on a vague answer).
- The effective "currently grilling" label is streamed (BUG-2), non-empty on resume.
- ``confirm`` advances CHECKPOINT → GRILLING.
- Both endpoints are protected (401 without a bearer); a bad ``action`` → 422.
- A mid-stream :class:`ModelAPIError` ends the stream with ``event: error``, not a 500.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from google.adk.sessions import BaseSessionService, InMemorySessionService

import workflows.nodes as nodes
from api.deps import get_auth_provider, get_discovery_session
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from cli import session as session_helpers
from cli.app import DiscoverySession
from config import AccessMode
from integration.model_client import GeminiModelClient, ModelAPIError
from schema import (
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    PhaseStatus,
)
from tests.test_integration import (
    ScriptedNodeClient,
    _finalize_response,
    _ingest_response,
    _specific_extraction,
    _vague_extraction,
)
from web.async_runner import run_async
from web.session_loader import web_session_id

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"
_APP = "career-engine"
_SID = web_session_id(_USER_ID)


# ── Auth fakes (copied from tests/test_api_write.py — no network) ──────────────


def _make_fake_verifier(sub: str = _USER_ID, email: str = "a@b.com") -> Any:
    """Return a network-free verifier returning fixed Google-style claims."""

    def _verifier(id_token: str) -> dict[str, Any]:
        return {"sub": sub, "email": email, "aud": "my-project", "iss": _GOOGLE_ISSUER}

    return _verifier


def _override_provider(verifier: Any) -> FirebaseAuthProvider:
    """Build a fully-injected provider decoupled from config (deterministic)."""
    return FirebaseAuthProvider(
        verifier=verifier,
        expected_audiences=["my-project"],
        allowed_issuers=[_GOOGLE_ISSUER],
    )


def _auth_headers() -> dict[str, str]:
    """Install the fake auth provider and return a bearer header."""
    app.dependency_overrides[get_auth_provider] = lambda: _override_provider(
        _make_fake_verifier()
    )
    return {"Authorization": "Bearer anything"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_model_client_factory() -> Iterator[None]:
    """Restore the global node model-client factory so this test can't leak."""
    original = nodes._client_factory
    yield
    nodes._client_factory = original


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a TestClient and clear any dependency overrides afterwards."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _build_session(
    responses: dict[str, str], *, service: BaseSessionService | None = None
) -> DiscoverySession:
    """Build a real DiscoverySession over a scripted node client + in-memory service."""
    svc = service or cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    client = ScriptedNodeClient(responses=responses)
    return DiscoverySession(
        user_id=_USER_ID,
        access_mode=AccessMode.BYOK,
        model_client=cast(GeminiModelClient, client),
        session_service=svc,
        app_name=_APP,
        session_id=_SID,
    )


def _override_session(session: DiscoverySession) -> None:
    """Inject a prebuilt DiscoverySession for every get_discovery_session call."""
    app.dependency_overrides[get_discovery_session] = lambda: session


def _collect_sse(client: TestClient, headers: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:
    """Stream ``GET /api/grill/stream`` and return an ordered [(event, data), …] list."""
    events: list[tuple[str, dict[str, Any]]] = []
    with client.stream("GET", "/api/grill/stream", headers=headers) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        current: str | None = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload = json.loads(line.split(":", 1)[1].strip())
                events.append((current or "", payload))
    return events


def _entry(
    title: str, org: str = "", status: EntryStatus = EntryStatus.NEEDS_QUANTIFYING
) -> Entry:
    return Entry(type=ExperienceType.FULL_TIME, title=title, org=org, status=status)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_grill_start_then_stream_emits_opening_question(client: TestClient) -> None:
    """POST start records history; the stream emits exactly one turn + a done frame."""
    session = _build_session(
        {
            "analyzing a career history": _ingest_response(["performance_engineering"]),
            "senior engineering colleague": "Tell me about a performance win.",
        }
    )
    _override_session(session)
    headers = _auth_headers()

    resp = client.post(
        "/api/grill",
        json={"action": "start", "history": "10 years perf engineering."},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["awaiting"] in {"question", "checkpoint", "complete"}

    events = _collect_sse(client, headers)
    kinds = [e for e, _ in events]
    assert kinds == ["turn", "done"], kinds
    turn_payload = events[0][1]
    assert turn_payload["next_question"] == "Tell me about a performance win."
    assert turn_payload["frontier_label"], "the currently-grilling label must be set"


def test_grill_answer_scripted_multi_turn_sequence(client: TestClient) -> None:
    """An ACCEPTED answer auto-advances (>1 turn); a VAGUE answer stays single-turn."""
    # ── Accepted: a single grillable entry, specific answer closes the last gap ──
    accepted = _build_session(
        {
            "analyzing a career history": _ingest_response(["performance_engineering"]),
            "senior engineering colleague": "Tell me about a perf win.",
            "data extraction assistant": _specific_extraction(),
            "assembling a master resume": _finalize_response(),
            "tailoring a master resume": json.dumps(
                {"tailored_summary": "Great fit.", "selected_achievements": []}
            ),
        }
    )
    _override_session(accepted)
    headers = _auth_headers()

    client.post(
        "/api/grill",
        json={"action": "start", "history": "10 years perf engineering."},
        headers=headers,
    )
    _collect_sse(client, headers)  # run the opening turn

    client.post(
        "/api/grill",
        json={"action": "answer", "answer": "cut p99 from 800ms to 120ms across 40 services"},
        headers=headers,
    )
    events = _collect_sse(client, headers)
    turn_events = [d for e, d in events if e == "turn"]
    assert len(turn_events) > 1, "an accepted answer must auto-advance to finalize"
    assert events[-1][0] == "done"
    assert events[-1][1]["is_complete"] is True

    # ── Vague: no story committed → a single probing follow-up, no auto-advance ──
    vague = _build_session(
        {
            "analyzing a career history": _ingest_response(["performance_engineering"]),
            "senior engineering colleague": "Tell me about a perf win.",
            "data extraction assistant": _vague_extraction(),
        }
    )
    _override_session(vague)

    client.post(
        "/api/grill",
        json={"action": "start", "history": "10 years perf engineering."},
        headers=headers,
    )
    _collect_sse(client, headers)  # opening turn

    client.post(
        "/api/grill",
        json={"action": "answer", "answer": "we got a lot faster"},
        headers=headers,
    )
    vague_events = _collect_sse(client, headers)
    vague_turns = [d for e, d in vague_events if e == "turn"]
    assert len(vague_turns) == 1, "a vague answer must not auto-advance"
    assert vague_turns[0]["next_question"], "a vague answer must surface a follow-up"
    assert vague_turns[0]["is_complete"] is False


async def test_grill_resume_mid_grill_emits_correct_frontier_label(
    client: TestClient,
) -> None:
    """On resume with a BLANK frontier, the streamed label names the next grillable entry."""
    svc = cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    grilled = _entry("Perf Eng", org="Acme", status=EntryStatus.GRILLED)
    pending = _entry("Team Lead", org="Globex", status=EntryStatus.NEEDS_QUANTIFYING)
    await session_helpers.create_session(
        session_service=svc,
        app_name=_APP,
        user_id=_USER_ID,
        session_id=_SID,
        initial_state=CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[grilled, pending],
            grill_frontier="",  # BUG-2: blank on resume, but a grillable entry remains
            question_count=1,
        ),
    )
    session = _build_session(
        {"senior engineering colleague": "Tell me about a Team Lead win."},
        service=svc,
    )
    _override_session(session)
    headers = _auth_headers()

    events = _collect_sse(client, headers)
    assert events[0][0] == "turn"
    assert events[0][1]["frontier_label"] == "Team Lead · Globex"


async def test_grill_confirm_checkpoint_clears_checkpoint(client: TestClient) -> None:
    """POST confirm + stream advances CHECKPOINT → GRILLING and clears the summary."""
    svc = cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    pending = _entry("Leadership Role")
    await session_helpers.create_session(
        session_service=svc,
        app_name=_APP,
        user_id=_USER_ID,
        session_id=_SID,
        initial_state=CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            work_timeline=[pending],
            grill_frontier=str(pending.entry_id),
            checkpoint_delta_summary="Recap. Accurate?",
            checkpoint_verified=False,
            question_count=5,
        ),
    )
    session = _build_session(
        {
            "summarizing progress": "Recap. Accurate?",
            "senior engineering colleague": "Tell me about a leadership win.",
        },
        service=svc,
    )
    _override_session(session)
    headers = _auth_headers()

    resp = client.post("/api/grill", json={"action": "confirm"}, headers=headers)
    assert resp.status_code == 200

    events = _collect_sse(client, headers)
    assert events[-1][0] == "done"
    assert events[-1][1]["phase"] == PhaseStatus.GRILLING.value

    state = await session.current_state()
    assert state.current_phase == PhaseStatus.GRILLING
    assert state.checkpoint_delta_summary == ""


def test_grill_requires_auth(client: TestClient) -> None:
    """Both grill endpoints return 401 without an Authorization header."""
    # Override the session dep so no vault/model client is ever touched even if reached.
    _override_session(_build_session({}))
    assert client.post("/api/grill", json={"action": "confirm"}).status_code == 401
    assert client.get("/api/grill/stream").status_code == 401


def test_grill_rejects_bad_action(client: TestClient) -> None:
    """A body with an out-of-enum action is rejected by FastAPI with 422."""
    _override_session(_build_session({}))
    headers = _auth_headers()
    resp = client.post("/api/grill", json={"action": "nope"}, headers=headers)
    assert resp.status_code == 422


def test_grill_rejects_empty_input(client: TestClient) -> None:
    """``start`` with blank history and ``answer`` with blank answer both 422 (no record)."""
    _override_session(_build_session({}))
    headers = _auth_headers()
    assert (
        client.post(
            "/api/grill", json={"action": "start", "history": "   "}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/grill", json={"action": "answer", "answer": ""}, headers=headers
        ).status_code
        == 422
    )


def test_grill_model_error_emits_error_event(client: TestClient) -> None:
    """A ModelAPIError raised mid-turn ends the stream with an error frame, not a 500."""

    class _RaisingClient:
        def generate(self, model_id: str, system: str, user: str) -> str:
            raise ModelAPIError("quota exhausted", is_rate_limited=True)

    svc = cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    session = DiscoverySession(
        user_id=_USER_ID,
        access_mode=AccessMode.BYOK,
        model_client=cast(GeminiModelClient, _RaisingClient()),
        session_service=svc,
        app_name=_APP,
        session_id=_SID,
    )
    _override_session(session)
    headers = _auth_headers()

    client.post(
        "/api/grill",
        json={"action": "start", "history": "10 years perf engineering."},
        headers=headers,
    )
    events = _collect_sse(client, headers)
    assert events[-1][0] == "error", events
    assert events[-1][1]["rate_limited"] is True
    assert events[-1][1]["message"]


# ── GET /api/grill — resume an existing session ───────────────────────────────


def test_grill_status_reports_no_session_for_a_new_user(client: TestClient) -> None:
    """A user with no session gets has_session=False → the client shows the start card."""
    from api.deps import get_session_service

    svc = cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    app.dependency_overrides[get_session_service] = lambda: svc

    resp = client.get("/api/grill", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_session"] is False
    assert body["awaiting"] == "idle"


def test_grill_status_rehydrates_the_pending_question(client: TestClient) -> None:
    """An existing session is reported WITH its persisted pending question.

    Regression (reported on qa): the Grill page decided what to render from in-memory
    state, so a fresh load always showed the "upload your résumé" start card — even with
    a live session, and even straight after "Grill me about this". The client needs this
    read to resume. It must cost NO model call: `current_question` is persisted state.
    """
    from api.deps import get_session_service
    from cli.session import create_session
    from config import get_settings
    from web.session_loader import web_session_id

    svc = cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    state = CareerEngineState(
        reference_date="2026-07-12",
        current_phase=PhaseStatus.GRILLING,
        current_question="What did that migration actually save?",
    )
    run_async(
        create_session(
            session_service=svc,
            app_name=get_settings().app_name,
            user_id=_USER_ID,
            session_id=web_session_id(_USER_ID),
            initial_state=state,
        )
    )
    app.dependency_overrides[get_session_service] = lambda: svc

    resp = client.get("/api/grill", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_session"] is True
    assert body["current_question"] == "What did that migration actually save?"
    assert body["awaiting"] == "question"


def test_grill_status_requires_auth(client: TestClient) -> None:
    assert client.get("/api/grill").status_code == 401
