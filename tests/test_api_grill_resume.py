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

from api.deps import get_auth_provider, get_discovery_session
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


@pytest.fixture
def client() -> Iterator[TestClient]:
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


def test_empty_file_rejected_422(client: TestClient) -> None:
    app.dependency_overrides[get_discovery_session] = lambda: _FakeSession()
    resp = client.post(
        "/api/grill/resume",
        files={"file": ("resume.pdf", b"", "application/pdf")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422
