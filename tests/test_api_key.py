"""Tests for BYOK key-management API (api/routes_key.py — parity P1).

Network-free: ``get_key_vault`` is overridden with an in-memory fake, so no test
touches Secret Manager. Auth fakes copied from tests/test_api_write.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import get_auth_provider, get_key_vault
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from auth.provider import KeyVaultError

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


def _make_fake_verifier(sub: str = _USER_ID, email: str = "a@b.com") -> Any:
    def _verifier(id_token: str) -> dict[str, Any]:
        return {"sub": sub, "email": email, "aud": "my-project", "iss": _GOOGLE_ISSUER}

    return _verifier


def _auth_headers() -> dict[str, str]:
    app.dependency_overrides[get_auth_provider] = lambda: FirebaseAuthProvider(
        verifier=_make_fake_verifier(),
        expected_audiences=["my-project"],
        allowed_issuers=[_GOOGLE_ISSUER],
    )
    return {"Authorization": "Bearer anything"}


class _FakeVault:
    """In-memory stand-in for SecretManagerKeyVault."""

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def store_key(self, user_id: str, api_key: str) -> None:
        self._keys[user_id] = api_key

    def key_exists(self, user_id: str) -> bool:
        return user_id in self._keys

    def fetch_key(self, user_id: str) -> str:
        if user_id not in self._keys:
            raise KeyVaultError("no key for user")
        return self._keys[user_id]

    def delete_key(self, user_id: str) -> None:
        self._keys.pop(user_id, None)


@pytest.fixture
def client() -> Iterator[TestClient]:
    vault = _FakeVault()
    app.dependency_overrides[get_key_vault] = lambda: vault
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_set_then_status_then_remove(client: TestClient) -> None:
    h = _auth_headers()
    # No key yet.
    assert client.get("/api/key", headers=h).json() == {"has_key": False}
    # Set a key → 204.
    assert client.post("/api/key", json={"api_key": "test-fake-key-abc123"}, headers=h).status_code == 204
    # Now present.
    assert client.get("/api/key", headers=h).json() == {"has_key": True}
    # Remove → 204, then absent.
    assert client.delete("/api/key", headers=h).status_code == 204
    assert client.get("/api/key", headers=h).json() == {"has_key": False}


def test_short_key_rejected_422(client: TestClient) -> None:
    resp = client.post("/api/key", json={"api_key": "short"}, headers=_auth_headers())
    assert resp.status_code == 422


def test_key_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/key").status_code == 401
    assert client.post("/api/key", json={"api_key": "test-fake-key-abc123"}).status_code == 401
    assert client.delete("/api/key").status_code == 401
