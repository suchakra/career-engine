"""Tests for the FastAPI auth boundary (api/main.py, api/deps.py, api/auth.py).

All tests inject a fake verifier via ``app.dependency_overrides`` so nothing
touches the network. The FastAPI TestClient drives the app synchronously.

Acceptance criteria verified (Phase 10.1):
- /api/health is an unauthenticated liveness probe.
- /api/me requires a valid bearer token and resolves the stable user_id +
  safe display email; the raw token is never echoed on failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import get_auth_provider
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from auth.provider import AuthenticationError

_GOOGLE_ISSUER = "https://accounts.google.com"


def _make_fake_verifier(
    sub: str = "user-123",
    email: str = "a@b.com",
) -> Any:
    """Return a network-free verifier returning fixed Google-style claims."""

    def _verifier(id_token: str) -> dict[str, Any]:
        return {
            "sub": sub,
            "email": email,
            "aud": "my-project",
            "iss": _GOOGLE_ISSUER,
        }

    return _verifier


def _override_provider(verifier: Any) -> FirebaseAuthProvider:
    """Build a fully-injected provider decoupled from config.

    Supplying BOTH ``expected_audiences`` and ``allowed_issuers`` keeps the
    provider from importing ``config.get_settings()`` (and its dotenv side
    effects), so the audience/issuer checks are deterministic and independent of
    any ``GCP_PROJECT_ID`` / ``firebase_project_id`` in the environment. The
    accepted audience matches the fake verifier's ``aud`` so the check passes.
    """
    return FirebaseAuthProvider(
        verifier=verifier,
        expected_audiences=["my-project"],
        allowed_issuers=[_GOOGLE_ISSUER],
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a TestClient and clear any dependency overrides afterwards."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_api_health_ok(client: TestClient) -> None:
    """/api/health returns 200 with {"status": "ok"} and needs no auth."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_auth_rejects_missing_token(client: TestClient) -> None:
    """/api/me with no Authorization header returns 401."""
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_api_me_resolves_user_id(client: TestClient) -> None:
    """/api/me with a valid bearer token returns the stable user_id + email."""
    app.dependency_overrides[get_auth_provider] = lambda: _override_provider(
        _make_fake_verifier(sub="user-123", email="a@b.com")
    )
    resp = client.get("/api/me", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "user-123"
    assert body["email"] == "a@b.com"


def test_api_me_rejects_invalid_token(client: TestClient) -> None:
    """/api/me with a token the verifier rejects returns 401 and never echoes it."""

    def _failing_verifier(id_token: str) -> dict[str, Any]:
        raise AuthenticationError("invalid token")

    app.dependency_overrides[get_auth_provider] = lambda: _override_provider(
        _failing_verifier
    )
    secret_token = "super-secret-token-value"
    resp = client.get("/api/me", headers={"Authorization": f"Bearer {secret_token}"})
    assert resp.status_code == 401
    assert secret_token not in resp.text
