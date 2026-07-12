"""Tests for the protected read APIs (api/routes_read.py, api/schemas.py).

Every test injects fakes via ``app.dependency_overrides`` so nothing touches the
network: a fake auth verifier resolves a ``user_id`` (copied from
``tests/test_api_auth.py``), and in-memory fakes stand in for the discovery
session service, workspace store, and ledger store.

Acceptance criteria verified (Phase 10.2):
- /api/dashboard, /api/portfolio, /api/jobs are protected (401 without a token)
  and return the exact typed JSON mirror of the pure view dataclasses.
- Missing session / empty workspace / no jobs degrade to a typed EMPTY payload
  (HTTP 200, never 500).
- A workspace ``ContractVersionError`` PROPAGATES (a schema mismatch must not
  masquerade as an empty, lost workspace).
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_auth_provider,
    get_ledger_store,
    get_session_service,
    get_workspace_store,
)
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from database.firestore_session import ContractVersionError
from schema import (
    Application,
    CareerEngineState,
    EmploymentType,
    Entry,
    EntryStatus,
    ExperienceType,
    InteractionLedger,
    JobMetadata,
    JobOpportunity,
    MatchStatus,
    PendingAction,
    SessionPreferences,
    StarStory,
    UserProfile,
    UserWorkspace,
    WorkModel,
)
from web.session_loader import web_session_id

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


# ── Auth fakes (copied from tests/test_api_auth.py — no network) ───────────────


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


# ── Read-path fakes (in-memory; no Firestore) ─────────────────────────────────


class _FakeSession:
    """Minimal ADK-session stand-in (``id`` + ``state`` + ``last_update_time``)."""

    def __init__(self, *, session_id: str, state: dict[str, Any]) -> None:
        self.id = session_id
        self.state = state
        self.last_update_time = 1.0


class _FakeSessionService:
    """In-memory session service exposing the async surface the loader uses."""

    def __init__(self, sessions: dict[str, _FakeSession]) -> None:
        self._sessions = sessions

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> _FakeSession | None:
        return self._sessions.get(session_id)

    async def list_sessions(self, *, app_name: str, user_id: str) -> Any:
        return SimpleNamespace(sessions=list(self._sessions.values()))


class _FakeWorkspaceStore:
    """In-memory workspace store; optionally raises to exercise degrade paths."""

    def __init__(self, workspace: UserWorkspace, *, error: Exception | None = None) -> None:
        self._workspace = workspace
        self._error = error

    def load(self, user_id: str) -> UserWorkspace:
        if self._error is not None:
            raise self._error
        return self._workspace


class _FakeLedgerStore:
    """In-memory ledger store exposing ``list_accepted`` + ``load_ledger``."""

    def __init__(
        self,
        accepted: list[JobOpportunity],
        *,
        rejected_companies: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._accepted = accepted
        self._rejected = rejected_companies or []
        self._error = error

    def list_accepted(self, user_id: str) -> list[JobOpportunity]:
        if self._error is not None:
            raise self._error
        return list(self._accepted)

    def load_ledger(self, user_id: str) -> InteractionLedger:
        if self._error is not None:
            raise self._error
        return InteractionLedger(rejected_companies=list(self._rejected))


# ── Sample data ───────────────────────────────────────────────────────────────


def _seeded_state() -> CareerEngineState:
    """A grilled entry with one metric-validated STAR story linked to it."""
    entry = Entry(
        type=ExperienceType.FULL_TIME,
        title="Senior Engineer",
        org="Acme",
        start_date="2020",
        end_date="2023",
        bullets=["Led the platform team"],
        status=EntryStatus.GRILLED,
        highlighted=True,
    )
    story = StarStory(
        entry_id=str(entry.entry_id),
        pillar="leadership",
        situation="Legacy pipeline was flaky",
        task="Stabilise deploys",
        action="Rebuilt CI",
        result="Cut failures by 40%",
        metrics_validated=True,
    )
    return CareerEngineState(
        reference_date="2026-07-07",
        work_timeline=[entry],
        extracted_star_stories=[story],
    )


def _seeded_workspace() -> UserWorkspace:
    """One tracked application with a follow-up pending action."""
    application = Application(company="Acme", job_title="Senior Engineer")
    pending = PendingAction(
        application_id=str(application.application_id),
        kind="follow_up",
        reason="Follow up with Acme",
    )
    return UserWorkspace(applications=[application], pending_actions=[pending])


def _seeded_job() -> JobOpportunity:
    """One previously-accepted job posting."""
    return JobOpportunity(
        job_id="job-1",
        metadata=JobMetadata(
            title="Product Manager",
            company="Globex",
            work_model=WorkModel.REMOTE,
            employment_type=EmploymentType.FULL_TIME,
            location="Remote",
            url="https://example.com/job-1",
        ),
        raw_description="Own the roadmap.",
        match_status=MatchStatus.ACCEPTED,
        ai_rationale="Strong roadmap ownership match.",
    )


def _seeded_session_service(state: CareerEngineState) -> _FakeSessionService:
    """A session service returning ``state`` under the canonical web session id."""
    session_id = web_session_id(_USER_ID)
    return _FakeSessionService(
        {session_id: _FakeSession(session_id=session_id, state=state.model_dump(mode="json"))}
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a TestClient and clear any dependency overrides afterwards."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── /api/dashboard ────────────────────────────────────────────────────────────


def test_dashboard_returns_typed_view(client: TestClient) -> None:
    """/api/dashboard returns the meter, pending actions, and application count."""
    app.dependency_overrides[get_session_service] = lambda: _seeded_session_service(
        _seeded_state()
    )
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        _seeded_workspace()
    )
    resp = client.get("/api/dashboard", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "documented" in body["progress_meter"]
    assert body["application_count"] == 1
    assert body["pending_actions"] == ["Follow up with Acme"]
    assert body["pending_actions_detail"][0]["kind"] == "follow_up"
    assert body["can_tailor"] is True
    assert body["can_start_grill"] is True
    assert body["can_find_jobs"] is True


def test_dashboard_empty_state_degrades(client: TestClient) -> None:
    """No session + empty workspace → typed empty payload, HTTP 200 not 500."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService({})
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace()
    )
    resp = client.get("/api/dashboard", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["application_count"] == 0
    assert body["pending_actions"] == []


def test_dashboard_workspace_failure_degrades(client: TestClient) -> None:
    """A transient workspace fault degrades to an empty workspace (not a 500)."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService({})
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(), error=RuntimeError("backend down")
    )
    resp = client.get("/api/dashboard", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["application_count"] == 0


def test_dashboard_contract_mismatch_propagates(client: TestClient) -> None:
    """A workspace ContractVersionError must NOT masquerade as an empty payload."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService({})
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(), error=ContractVersionError("major mismatch")
    )
    with pytest.raises(ContractVersionError):
        client.get("/api/dashboard", headers=_auth_headers())


def test_dashboard_requires_auth(client: TestClient) -> None:
    """/api/dashboard with no Authorization header returns 401."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService({})
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace()
    )
    resp = client.get("/api/dashboard")
    assert resp.status_code == 401


# ── /api/portfolio ────────────────────────────────────────────────────────────


def test_portfolio_returns_entries_with_stories(client: TestClient) -> None:
    """/api/portfolio returns the timeline entries with their STAR stories."""
    app.dependency_overrides[get_session_service] = lambda: _seeded_session_service(
        _seeded_state()
    )
    resp = client.get("/api/portfolio", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_empty"] is False
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["title"] == "Senior Engineer"
    assert entry["org"] == "Acme"
    assert entry["highlighted"] is True
    assert entry["story_count"] == 1
    story = entry["stories"][0]
    assert story["result"] == "Cut failures by 40%"
    assert story["metric_validated"] is True


def test_portfolio_empty_state_degrades(client: TestClient) -> None:
    """No session → typed empty portfolio payload, HTTP 200 not 500."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService({})
    resp = client.get("/api/portfolio", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_empty"] is True
    assert body["entries"] == []


def test_portfolio_requires_auth(client: TestClient) -> None:
    """/api/portfolio with no Authorization header returns 401."""
    app.dependency_overrides[get_session_service] = lambda: _FakeSessionService({})
    resp = client.get("/api/portfolio")
    assert resp.status_code == 401


# ── /api/jobs ─────────────────────────────────────────────────────────────────


def test_jobs_returns_accepted_cards(client: TestClient) -> None:
    """/api/jobs returns previously-accepted matches as strong-match cards."""
    app.dependency_overrides[get_ledger_store] = lambda: _FakeLedgerStore([_seeded_job()])
    resp = client.get("/api/jobs", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_empty"] is False
    assert body["ran"] is False
    assert body["for_review"] == []
    assert len(body["accepted"]) == 1
    card = body["accepted"][0]
    assert card["job_id"] == "job-1"
    assert card["company"] == "Globex"
    assert card["status"] == "accepted"
    assert card["work_model"] == "remote"


def test_jobs_hides_rejected_company(client: TestClient) -> None:
    """A dismissed company is dropped from the accepted list."""
    app.dependency_overrides[get_ledger_store] = lambda: _FakeLedgerStore(
        [_seeded_job()], rejected_companies=["Globex"]
    )
    resp = client.get("/api/jobs", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["accepted"] == []


def test_jobs_empty_state_degrades(client: TestClient) -> None:
    """No persisted jobs → typed empty JobsView payload, HTTP 200 not 500."""
    app.dependency_overrides[get_ledger_store] = lambda: _FakeLedgerStore([])
    resp = client.get("/api/jobs", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_empty"] is True
    assert body["accepted"] == []
    assert body["for_review"] == []


def test_jobs_backend_fault_degrades(client: TestClient) -> None:
    """A transient ledger fault degrades to an empty payload (HTTP 200 not 500)."""
    app.dependency_overrides[get_ledger_store] = lambda: _FakeLedgerStore(
        [_seeded_job()], error=RuntimeError("firestore down")
    )
    resp = client.get("/api/jobs", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_empty"] is True
    assert body["accepted"] == []


def test_jobs_requires_auth(client: TestClient) -> None:
    """/api/jobs with no Authorization header returns 401."""
    app.dependency_overrides[get_ledger_store] = lambda: _FakeLedgerStore([])
    resp = client.get("/api/jobs")
    assert resp.status_code == 401


# ── GET /api/profile + GET /api/preferences ───────────────────────────────────
#
# The 10.3 writes shipped without these reads, so the client's Profile/Preferences
# forms had nothing to hydrate from — a saved profile looked like it never persisted.


def test_profile_returns_the_persisted_profile(client: TestClient) -> None:
    """/api/profile returns EVERY persisted field, not just the ones a form edits."""
    profile = UserProfile(
        name="Ada", email="ada@x.com", phone="+1", location="Remote", links=["https://gh/ada"]
    )
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(profile=profile)
    )
    resp = client.get("/api/profile", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    # Every field round-trips — the client needs email/phone/links too, or a save that
    # only edits name+location would blank them (the store does a full-document write).
    assert body["name"] == "Ada"
    assert body["email"] == "ada@x.com"
    assert body["phone"] == "+1"
    assert body["location"] == "Remote"
    assert body["links"] == ["https://gh/ada"]


def test_profile_empty_for_a_new_user(client: TestClient) -> None:
    """A user with no saved profile gets an empty one (never a 404/500)."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(UserWorkspace())
    resp = client.get("/api/profile", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["name"] == ""


def test_profile_requires_auth(client: TestClient) -> None:
    assert client.get("/api/profile").status_code == 401


def test_preferences_returns_the_persisted_rubric(client: TestClient) -> None:
    """/api/preferences returns every rubric field (incl. ones no form edits yet)."""
    prefs = SessionPreferences(
        target_roles=["Staff Engineer"],
        dealbreakers=["on-site"],
        nice_to_haves=["remote-first"],
    )
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(discovery_preferences=prefs)
    )
    resp = client.get("/api/preferences", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_roles"] == ["Staff Engineer"]
    assert body["dealbreakers"] == ["on-site"]
    assert body["nice_to_haves"] == ["remote-first"]


def test_preferences_empty_for_a_new_user(client: TestClient) -> None:
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(UserWorkspace())
    resp = client.get("/api/preferences", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["target_roles"] == []


def test_preferences_requires_auth(client: TestClient) -> None:
    assert client.get("/api/preferences").status_code == 401


def test_profile_degrades_to_empty_on_store_fault(client: TestClient) -> None:
    """A transient store fault yields an EMPTY profile, never a 500 (module contract)."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(), error=RuntimeError("firestore down")
    )
    resp = client.get("/api/profile", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["name"] == ""


def test_profile_propagates_contract_version_error(client: TestClient) -> None:
    """A schema mismatch must NOT masquerade as an empty (lost) profile."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(), error=ContractVersionError("bad major")
    )
    with pytest.raises(ContractVersionError):
        client.get("/api/profile", headers=_auth_headers())


def test_preferences_degrades_to_empty_on_store_fault(client: TestClient) -> None:
    """A transient store fault yields an EMPTY rubric, never a 500."""
    app.dependency_overrides[get_workspace_store] = lambda: _FakeWorkspaceStore(
        UserWorkspace(), error=RuntimeError("firestore down")
    )
    resp = client.get("/api/preferences", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["target_roles"] == []
