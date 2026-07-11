"""Tests for the job-discovery run API (api/routes_jobs.py — parity P2).

Network-free: the BYOK vault + stores are fakes, and the discovery RUN
(``run_web_discovery``) + primary wiring + preferences load are monkeypatched, so no
model / MCP / Firestore is touched. Verifies the endpoint threads key→prefs→ledger→run
and returns the fresh JobsView (and 409 without a key, 401 without auth).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_auth_provider,
    get_key_vault,
    get_ledger_store,
    get_workspace_store,
)
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider
from auth.provider import KeyVaultError
from discovery.primary import DiscoveryResult
from schema import InteractionLedger, SessionPreferences

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


def _auth_headers() -> dict[str, str]:
    def _verifier(id_token: str) -> dict[str, Any]:
        return {"sub": _USER_ID, "email": "a@b.com", "aud": "p", "iss": _GOOGLE_ISSUER}

    app.dependency_overrides[get_auth_provider] = lambda: FirebaseAuthProvider(
        verifier=_verifier, expected_audiences=["p"], allowed_issuers=[_GOOGLE_ISSUER]
    )
    return {"Authorization": "Bearer x"}


class _FakeVault:
    def __init__(self, has: bool = True) -> None:
        self._has = has

    def fetch_key(self, user_id: str) -> str:
        if not self._has:
            raise KeyVaultError("no key")
        return "test-fake-key-123456"

    def key_exists(self, user_id: str) -> bool:
        return self._has


class _FakeLedgerStore:
    def load_ledger(self, user_id: str) -> InteractionLedger:
        return InteractionLedger()

    def list_accepted(self, user_id: str) -> list[Any]:
        return []

    def record_accepted(self, user_id: str, jobs: list[Any]) -> int:
        return 0


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_discover_runs_and_returns_fresh_view(client: TestClient, monkeypatch: Any) -> None:
    app.dependency_overrides[get_key_vault] = lambda: _FakeVault(has=True)
    app.dependency_overrides[get_ledger_store] = lambda: _FakeLedgerStore()
    app.dependency_overrides[get_workspace_store] = lambda: object()
    # Isolate from model / MCP / Firestore:
    monkeypatch.setattr(
        "api.routes_jobs.load_discovery_preferences",
        lambda store, *, user_id: SessionPreferences(),
    )
    monkeypatch.setattr("api.routes_jobs.build_web_primary", lambda **kw: object())
    monkeypatch.setattr(
        "api.routes_jobs.run_web_discovery",
        lambda **kw: DiscoveryResult(iterations=2, hard_rejected_count=3),
    )

    resp = client.post("/api/jobs/discover", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran"] is True
    assert body["iterations"] == 2
    assert body["hard_rejected_count"] == 3
    assert body["accepted"] == []


def test_discover_requires_a_byok_key(client: TestClient) -> None:
    app.dependency_overrides[get_key_vault] = lambda: _FakeVault(has=False)
    resp = client.post("/api/jobs/discover", headers=_auth_headers())
    assert resp.status_code == 409


def test_discover_requires_auth(client: TestClient) -> None:
    assert client.post("/api/jobs/discover").status_code == 401
