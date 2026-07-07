"""Tests for the protected write APIs (api/routes_write.py, api/schemas.py).

Every test injects fakes via ``app.dependency_overrides`` so nothing touches the
network: a fake auth verifier resolves a ``user_id`` (copied from
``tests/test_api_read.py``), an in-memory workspace store gives a real
``.load``/``.save`` round-trip, and an in-memory ADK-style session service gives a
real ``get_session``/``create_session``/``append_event`` round-trip for the
experience write.

Acceptance criteria verified (Phase 10.3):
- POST /api/profile, PUT /api/preferences, POST /api/applications,
  POST /api/experience are protected (401 without a token).
- Each happy path WRITES then RE-READS the value back through the same fake
  store/service (round-trip) and asserts the response body shape.
- A malformed body yields 422 (FastAPI validates against the Pydantic model).
- An empty UserProfile write persists (and re-reads) an empty profile — exactly
  what the store already does.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import get_auth_provider, get_session_service, get_workspace_store
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from schema import (
    CareerEngineState,
    Entry,
    ExperienceType,
    SessionPreferences,
    UserProfile,
    UserWorkspace,
)
from web.session_loader import web_session_id

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


# ── Auth fakes (copied from tests/test_api_read.py — no network) ───────────────


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


# ── Write-path fakes (in-memory; no Firestore) ────────────────────────────────


class _FakeWorkspaceStore:
    """In-memory workspace store with a real sync ``.load``/``.save`` round-trip."""

    def __init__(self) -> None:
        self._data: dict[str, UserWorkspace] = {}

    def load(self, user_id: str) -> UserWorkspace:
        return self._data.get(user_id, UserWorkspace())

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        self._data[user_id] = workspace


class _FakeSession:
    """Minimal ADK-session stand-in (``id`` + ``state`` + ``last_update_time``)."""

    def __init__(self, *, session_id: str, state: dict[str, Any]) -> None:
        self.id = session_id
        self.state = state
        self.last_update_time = 1.0


class _FakeSessionService:
    """In-memory session service with the async surface the write path uses.

    Mirrors what ``web.portfolio_store._aadd_manual_entry`` (via
    ``cli.session.get_session_state_if_exists`` and ``_patch_session``) and
    ``web.session_loader.atry_load_latest_discovery_state`` call:
    ``get_session`` returns a COPY (like ADK) so external state changes are only
    committed through ``append_event``'s ``state_delta``.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _FakeSession] = {}

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> _FakeSession | None:
        stored = self._sessions.get(session_id)
        if stored is None:
            return None
        return _FakeSession(session_id=stored.id, state=dict(stored.state))

    async def create_session(
        self, *, app_name: str, user_id: str, session_id: str, state: dict[str, Any]
    ) -> _FakeSession:
        session = _FakeSession(session_id=session_id, state=dict(state))
        self._sessions[session_id] = session
        return session

    async def append_event(self, session: _FakeSession, event: Any) -> None:
        stored = self._sessions[session.id]
        delta = getattr(event.actions, "state_delta", None) or {}
        stored.state.update(delta)
        stored.last_update_time += 1.0

    async def list_sessions(self, *, app_name: str, user_id: str) -> Any:
        return SimpleNamespace(sessions=list(self._sessions.values()))

    def state_for(self, user_id: str) -> CareerEngineState:
        """Round-trip helper: validate the canonical session's persisted state."""
        return CareerEngineState.model_validate(self._sessions[web_session_id(user_id)].state)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a TestClient and clear any dependency overrides afterwards."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── POST /api/profile ─────────────────────────────────────────────────────────


def test_profile_write_round_trip(client: TestClient) -> None:
    """POST /api/profile persists the profile and re-reads it back (round-trip)."""
    store = _FakeWorkspaceStore()
    app.dependency_overrides[get_workspace_store] = lambda: store
    profile = UserProfile(
        name="Ada", email="ada@x.com", location="Remote", links=["https://gh/ada"]
    )
    resp = client.post(
        "/api/profile", json=profile.model_dump(mode="json"), headers=_auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Ada"
    assert body["email"] == "ada@x.com"
    assert body["links"] == ["https://gh/ada"]
    # Persisted in the store (read-modify-write preserved the rest of the workspace).
    assert store.load(_USER_ID).profile.name == "Ada"


def test_profile_empty_write_persists_empty(client: TestClient) -> None:
    """An empty UserProfile persists (and re-reads) empty — exactly as the store does."""
    store = _FakeWorkspaceStore()
    app.dependency_overrides[get_workspace_store] = lambda: store
    resp = client.post("/api/profile", json={}, headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == ""
    assert body["links"] == []
    assert store.load(_USER_ID).profile.name == ""


def test_profile_write_rejects_malformed_body(client: TestClient) -> None:
    """A body whose field has the wrong type is rejected by FastAPI with 422."""
    store = _FakeWorkspaceStore()
    app.dependency_overrides[get_workspace_store] = lambda: store
    # ``name`` must be a str; a list is invalid → 422 (no store call happens).
    resp = client.post(
        "/api/profile", json={"name": ["not", "a", "string"]}, headers=_auth_headers()
    )
    assert resp.status_code == 422


def test_profile_write_requires_auth(client: TestClient) -> None:
    """POST /api/profile with no Authorization header returns 401."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore()
    resp = client.post("/api/profile", json={})
    assert resp.status_code == 401


# ── PUT /api/preferences ──────────────────────────────────────────────────────


def test_preferences_write_round_trip(client: TestClient) -> None:
    """PUT /api/preferences persists the rubric and re-reads it back (round-trip)."""
    store = _FakeWorkspaceStore()
    app.dependency_overrides[get_workspace_store] = lambda: store
    prefs = SessionPreferences(
        target_roles=["PM"], dealbreakers=["on-site"], nice_to_haves=["remote"]
    )
    resp = client.put(
        "/api/preferences", json=prefs.model_dump(mode="json"), headers=_auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_roles"] == ["PM"]
    assert body["dealbreakers"] == ["on-site"]
    assert body["nice_to_haves"] == ["remote"]
    # Persisted in the store.
    assert store.load(_USER_ID).discovery_preferences.nice_to_haves == ["remote"]


def test_preferences_write_requires_auth(client: TestClient) -> None:
    """PUT /api/preferences with no Authorization header returns 401."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore()
    resp = client.put("/api/preferences", json={})
    assert resp.status_code == 401


# ── POST /api/applications ────────────────────────────────────────────────────


def test_application_write_round_trip(client: TestClient) -> None:
    """POST /api/applications records the application and re-reads it (round-trip)."""
    store = _FakeWorkspaceStore()
    app.dependency_overrides[get_workspace_store] = lambda: store
    req = {
        "company": "Globex",
        "job_title": "Product Manager",
        "jd_text": "Own the roadmap.",
        "tailored_resume_json": "{}",
    }
    resp = client.post("/api/applications", json=req, headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["company"] == "Globex"
    assert body["job_title"] == "Product Manager"
    assert body["status"] == "applied"
    # applied_on is the injected clock computed at the endpoint boundary.
    assert body["applied_on"] == date.today().isoformat()
    # Persisted in the store.
    apps = store.load(_USER_ID).applications
    assert len(apps) == 1
    assert apps[0].company == "Globex"
    assert apps[0].tailored_resume_json == "{}"


def test_application_write_rejects_missing_field(client: TestClient) -> None:
    """A body missing a required field is rejected by FastAPI with 422."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore()
    resp = client.post(
        "/api/applications",
        json={"company": "Globex"},  # missing job_title / jd_text / tailored_resume_json
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_application_write_requires_auth(client: TestClient) -> None:
    """POST /api/applications with no Authorization header returns 401."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore()
    resp = client.post(
        "/api/applications",
        json={
            "company": "Globex",
            "job_title": "PM",
            "jd_text": "x",
            "tailored_resume_json": "{}",
        },
    )
    assert resp.status_code == 401


# ── POST /api/experience ──────────────────────────────────────────────────────


def test_experience_write_persists_entry(client: TestClient) -> None:
    """POST /api/experience appends the entry to a fresh canonical session."""
    svc = _FakeSessionService()
    app.dependency_overrides[get_session_service] = lambda: svc
    entry = Entry(type=ExperienceType.PROJECT, title="Built X", org="Acme")
    resp = client.post(
        "/api/experience", json=entry.model_dump(mode="json"), headers=_auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entry_id"] == str(entry.entry_id)
    assert body["title"] == "Built X"
    assert body["org"] == "Acme"
    assert body["entry_count"] == 1
    # Round-trip: the canonical session now holds the persisted entry.
    state = svc.state_for(_USER_ID)
    assert [e.title for e in state.work_timeline] == ["Built X"]


def test_experience_write_appends_to_existing_session(client: TestClient) -> None:
    """A second POST /api/experience appends to the existing session (patch path)."""
    svc = _FakeSessionService()
    app.dependency_overrides[get_session_service] = lambda: svc
    first = Entry(type=ExperienceType.PROJECT, title="First", org="A")
    second = Entry(type=ExperienceType.PROJECT, title="Second", org="B")
    client.post("/api/experience", json=first.model_dump(mode="json"), headers=_auth_headers())
    resp = client.post(
        "/api/experience", json=second.model_dump(mode="json"), headers=_auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entry_count"] == 2
    assert body["title"] == "Second"
    # Round-trip: both entries are persisted in order.
    state = svc.state_for(_USER_ID)
    assert [e.title for e in state.work_timeline] == ["First", "Second"]


def test_experience_write_rejects_missing_title(client: TestClient) -> None:
    """An Entry body missing the required ``title`` is rejected with 422."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService()
    resp = client.post("/api/experience", json={"org": "Acme"}, headers=_auth_headers())
    assert resp.status_code == 422


def test_experience_write_requires_auth(client: TestClient) -> None:
    """POST /api/experience with no Authorization header returns 401."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService()
    resp = client.post("/api/experience", json={"title": "Built X"})
    assert resp.status_code == 401
