"""Tests for résumé-upload grill seeding (POST /api/grill/resume — parity P3).

Network-free: ``get_discovery_session`` is overridden with a fake session, and
``parse_resume`` (the multimodal vision parser) is monkeypatched, so no model / MCP /
Firestore is touched. Auth fakes copied from tests/test_api_write.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import get_auth_provider, get_discovery_session, get_session_service
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from schema import CareerEngineState

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


def _auth_headers() -> dict[str, str]:
    def _verifier(id_token: str) -> dict[str, Any]:
        return {"sub": _USER_ID, "email": "a@b.com", "aud": "p", "iss": _GOOGLE_ISSUER}

    app.dependency_overrides[get_auth_provider] = lambda: FirebaseAuthProvider(
        verifier=_verifier, expected_audiences=["p"], allowed_issuers=[_GOOGLE_ISSUER]
    )
    return {"Authorization": "Bearer x"}


class _FakeSession:
    """Records the create(...) call; returns a fresh state."""

    model_client = object()

    def __init__(self) -> None:
        self.created: tuple[str, Any] | None = None

    async def create(
        self, raw_history_text: str, *, reference_date: str = "", work_timeline: Any = None
    ) -> None:
        self.created = (raw_history_text, work_timeline)

    async def current_state(self) -> CareerEngineState:
        return CareerEngineState()


class _NoSessionService:
    """A session service holding NOTHING — so the merge finds no session to merge into
    and the route falls through to create(), which is the first-upload path."""

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a TestClient with EVERY Firestore-backed dep faked.

    ``get_session_service`` is overridden here, not per-test: FastAPI resolves it eagerly,
    so a route that merely *declares* it would construct a real ``FirestoreSessionService``
    and reach for credentials. That passes locally (ADC) and fails in CI — which is
    exactly how this fixture broke when the résumé route gained the merge dependency.
    """
    app.dependency_overrides[get_session_service] = lambda: _NoSessionService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_resume_upload_parses_and_seeds_the_grill(
    client: TestClient, monkeypatch: Any
) -> None:
    session = _FakeSession()
    app.dependency_overrides[get_discovery_session] = lambda: session
    # Vision parse → two entries (monkeypatched; no model call).
    monkeypatch.setattr(
        "api.routes_grill.parse_resume", lambda data, mime, *, client: ["e1", "e2"]
    )

    resp = client.post(
        "/api/grill/resume",
        files={"file": ("resume.pdf", b"%PDF-fake-bytes", "application/pdf")},
        headers=_auth_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"phase", "frontier_label", "awaiting"}
    # The session was seeded from the parsed entries (empty history + work_timeline).
    assert session.created is not None
    assert session.created[1] == ["e1", "e2"]


def test_resume_upload_requires_auth(client: TestClient) -> None:
    # Explicit get_current_user_id dep enforces 401 even when the session is overridden.
    app.dependency_overrides[get_discovery_session] = lambda: _FakeSession()
    resp = client.post(
        "/api/grill/resume",
        files={"file": ("r.pdf", b"x", "application/pdf")},
    )
    assert resp.status_code == 401


def test_empty_file_rejected_422(client: TestClient) -> None:
    app.dependency_overrides[get_discovery_session] = lambda: _FakeSession()
    resp = client.post(
        "/api/grill/resume",
        files={"file": ("resume.pdf", b"", "application/pdf")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


# ── CQ-2: a RE-upload merges into the existing session; it never clobbers ──────


def test_reupload_merges_into_the_existing_session_and_never_creates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The data-loss fix: when a session exists, the upload MERGES — create is not called.

    ``session.create`` is last-write-wins, so calling it on a second upload destroyed the
    whole CareerEngineState. The route must merge instead, and must only create when
    there is genuinely no session to merge into.
    """
    from schema import Entry, ExperienceType

    parsed = [Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Texada")]
    monkeypatch.setattr("api.routes_grill.parse_resume", lambda *a, **k: parsed)

    merged_with: dict[str, Any] = {}

    async def _fake_merge(session_service: Any, *, app_name: str, user_id: str, entries: Any) -> str:
        merged_with.update(user_id=user_id, entries=entries)
        return "web-user-123"  # a session existed → merged

    monkeypatch.setattr("api.routes_grill.amerge_parsed_entries", _fake_merge)

    session = _FakeSession()
    app.dependency_overrides[get_discovery_session] = lambda: session

    resp = client.post(
        "/api/grill/resume",
        files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
        headers=_auth_headers(),
    )

    assert resp.status_code == 200
    assert merged_with["user_id"] == _USER_ID
    assert merged_with["entries"] == parsed
    assert session.created is None, "create() must NOT run when a session already exists"


def test_first_upload_still_creates_the_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No session to merge into (merge returns None) → the first upload creates one."""
    from schema import Entry, ExperienceType

    parsed = [Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Texada")]
    monkeypatch.setattr("api.routes_grill.parse_resume", lambda *a, **k: parsed)

    async def _no_session(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr("api.routes_grill.amerge_parsed_entries", _no_session)

    session = _FakeSession()
    app.dependency_overrides[get_discovery_session] = lambda: session

    resp = client.post(
        "/api/grill/resume",
        files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
        headers=_auth_headers(),
    )

    assert resp.status_code == 200
    assert session.created is not None
    assert session.created[1] == parsed
