"""Tests for the tailor + résumé-export API (api/routes_tailor.py — Phase 10.6b).

Network-free: ``get_discovery_session`` is overridden with a fake session (a seeded
state + a dummy model client), and ``tailor_structured_resume`` is monkeypatched to a
stub, so no BYOK vault / ``GeminiModelClient`` / model network is ever touched. The
render endpoint needs no key (deterministic renderers) and exercises the real
Markdown / WeasyPrint / python-docx paths. Auth fakes copied from tests/test_api_write.py.

Acceptance (Phase 10.6b):
- ``POST /api/tailor`` returns the structured résumé (contact/summary/skills/experience).
- ``POST /api/resume/{fmt}`` renders md/pdf/docx bytes with the right content-type; an
  unknown ``fmt`` → 422.
- Both endpoints are protected (401 without a bearer).

Acceptance (parity P4c):
- ``POST /api/master-resume`` assembles every validated story from the caller's session
  through the REAL (deterministic) ``master_structured_resume`` — the state loader is
  stubbed, the builder is not — and needs NO BYOK key. Protected (401 without a bearer).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.deps import get_auth_provider, get_discovery_session, get_session_service
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType, StarStory
from web.resume_builder import Contact, ResumeLine, RoleBlock, StructuredResume

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


# ── Auth fakes (copied from tests/test_api_write.py — no network) ──────────────


def _make_fake_verifier(sub: str = _USER_ID, email: str = "a@b.com") -> Any:
    def _verifier(id_token: str) -> dict[str, Any]:
        return {"sub": sub, "email": email, "aud": "my-project", "iss": _GOOGLE_ISSUER}

    return _verifier


def _override_provider(verifier: Any) -> FirebaseAuthProvider:
    return FirebaseAuthProvider(
        verifier=verifier,
        expected_audiences=["my-project"],
        allowed_issuers=[_GOOGLE_ISSUER],
    )


def _auth_headers() -> dict[str, str]:
    app.dependency_overrides[get_auth_provider] = lambda: _override_provider(
        _make_fake_verifier()
    )
    return {"Authorization": "Bearer anything"}


class _FakeSession:
    """Minimal stand-in for DiscoverySession used by the tailor route."""

    model_client = object()

    async def current_state(self) -> CareerEngineState:
        return CareerEngineState()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


_SAMPLE = StructuredResume(
    contact=Contact(name="Jane Doe", email="jane@example.com", location="Berlin"),
    summary="Staff engineer with a distributed-systems focus.",
    skills=["Python", "Distributed Systems"],
    experience=[RoleBlock(title="Senior Engineer", org="Acme", dates="2022-now",
                          bullets=[ResumeLine(text="Cut p95 40%")])],
    education=[],
)


def _resume_body() -> dict[str, Any]:
    return {
        "contact": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "",
            "location": "Berlin",
            "links": [],
        },
        "summary": "Staff engineer with a distributed-systems focus.",
        "skills": ["Python", "Distributed Systems"],
        "experience": [
            {"title": "Senior Engineer", "org": "Acme", "dates": "2022-now",
             "bullets": [{"text": "Cut p95 40%"}]}
        ],
        "education": [],
    }


# ── POST /api/tailor ──────────────────────────────────────────────────────────


def test_tailor_returns_structured_resume(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "api.routes_tailor.tailor_structured_resume", lambda *a, **k: _SAMPLE
    )
    app.dependency_overrides[get_discovery_session] = lambda: _FakeSession()

    resp = client.post(
        "/api/tailor",
        json={"jd_text": "We're hiring a Staff Engineer.", "instructions": "Emphasise cloud."},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["contact"]["name"] == "Jane Doe"
    assert body["skills"] == ["Python", "Distributed Systems"]
    assert body["experience"][0]["org"] == "Acme"


def test_tailor_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/tailor", json={"jd_text": "x"})
    assert resp.status_code == 401


# ── POST /api/resume/{fmt} ────────────────────────────────────────────────────


def test_render_markdown(client: TestClient) -> None:
    resp = client.post("/api/resume/md", json=_resume_body(), headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Jane Doe" in resp.text


def test_render_pdf(client: TestClient) -> None:
    resp = client.post("/api/resume/pdf", json=_resume_body(), headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_render_docx(client: TestClient) -> None:
    resp = client.post("/api/resume/docx", json=_resume_body(), headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert resp.content[:2] == b"PK"  # DOCX is a zip container


def test_render_rejects_unknown_format(client: TestClient) -> None:
    resp = client.post("/api/resume/txt", json=_resume_body(), headers=_auth_headers())
    assert resp.status_code == 422


def test_render_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/resume/md", json=_resume_body())
    assert resp.status_code == 401


# ── POST /api/master-resume (parity P4c) ──────────────────────────────────────


def _seeded_state() -> CareerEngineState:
    """A session with one grilled role + one education entry and two validated stories."""
    job = Entry(
        type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme",
        start_date="2020", end_date="2023", status=EntryStatus.GRILLED,
    )
    edu = Entry(
        type=ExperienceType.EDUCATION, title="BSc Computer Science", org="MIT",
        start_date="2016", end_date="2020", status=EntryStatus.SUMMARIZED,
    )
    stories = [
        StarStory(
            story_id=uuid4(), entry_id=str(job.entry_id), pillar="delivery",
            result=result, metrics_validated=True,
        )
        for result in ("Cut p99 latency 40%", "Shipped billing v2")
    ]
    return CareerEngineState(
        work_timeline=[job, edu],
        extracted_star_stories=stories,
        professional_summary="Staff engineer.",
    )


def _stub_state_loader(monkeypatch: Any, state: CareerEngineState) -> None:
    """Stub only the STATE LOAD — the résumé assembly under test stays real."""

    async def _load(*args: Any, **kwargs: Any) -> CareerEngineState:
        return state

    monkeypatch.setattr("api.routes_tailor.atry_load_latest_discovery_state", _load)
    # The route's session_service is passed straight to the (stubbed) loader.
    app.dependency_overrides[get_session_service] = lambda: object()


def test_master_resume_assembles_all_validated_stories(
    client: TestClient, monkeypatch: Any
) -> None:
    """Every validated story lands on the résumé, grouped by role, with the summary."""
    _stub_state_loader(monkeypatch, _seeded_state())

    resp = client.post("/api/master-resume", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "Staff engineer."
    assert body["skills"] == []  # skills are JD-aligned in the tailored pass only
    assert [b["org"] for b in body["experience"]] == ["Acme"]
    assert len(body["experience"][0]["bullets"]) == 2  # no JD selection → all stories
    assert [b["org"] for b in body["education"]] == ["MIT"]


def test_master_resume_needs_no_byok_key(client: TestClient, monkeypatch: Any) -> None:
    """The assembly is deterministic, so a caller with NO key still gets a 200.

    ``get_discovery_session`` (the 409-if-no-key gate) is deliberately NOT a dependency
    of this route; overriding it to explode proves the route never resolves it.
    """
    _stub_state_loader(monkeypatch, CareerEngineState())

    def _explode() -> None:
        raise AssertionError("master-resume must not require a BYOK key")

    app.dependency_overrides[get_discovery_session] = _explode

    resp = client.post("/api/master-resume", headers=_auth_headers())
    assert resp.status_code == 200
    # No validated stories → an empty résumé, not an error (mirrors GET /api/portfolio).
    assert resp.json()["experience"] == []


def test_master_resume_requires_auth(client: TestClient) -> None:
    assert client.post("/api/master-resume").status_code == 401
