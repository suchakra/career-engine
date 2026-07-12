"""Tests for the protected portfolio-action APIs (api/routes_portfolio.py).

Parity P4b: thin transport over ``web.portfolio_store``'s sync mutation bridges
(``set_grill_frontier`` / ``set_entry_highlight`` / ``delete_star_story``). These
tests inject fakes via ``app.dependency_overrides`` so nothing touches the network:
a fake auth verifier resolves a ``user_id`` (copied from ``tests/test_api_read.py``)
and a dummy session service satisfies the ``get_session_service`` dependency without
building a Firestore client. The store bridges themselves are monkeypatched — the
routes are pure transport, so we assert (a) the bridge is called with the right args,
(b) a truthy return → 204, and (c) a ``None`` return → 404.

Acceptance criteria verified:
- POST /api/experience/{id}/grill, POST /api/experience/{id}/highlight,
  DELETE /api/story/{id} are protected (401 without a token).
- Happy path returns 204 and forwards ``user_id`` + path/body params to the bridge.
- A ``None`` bridge return (no session / no such entry) maps to 404.
- A malformed highlight body yields 422 (FastAPI validates the Pydantic model).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes_portfolio as routes_portfolio
from api.deps import get_auth_provider, get_session_service
from api.main import app
from auth.firebase_auth import FirebaseAuthProvider

_GOOGLE_ISSUER = "https://accounts.google.com"
_USER_ID = "user-123"


# ── Auth fakes (copied from tests/test_api_read.py — no network) ───────────────


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


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a TestClient with a dummy session service; clear overrides afterwards.

    ``get_session_service`` normally constructs a real ``FirestoreSessionService``
    (network). The routes only pass it through to the (monkeypatched) sync bridge,
    so a sentinel object is sufficient.
    """
    app.dependency_overrides[get_session_service] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── POST /api/experience/{id}/grill ───────────────────────────────────────────


def test_grill_entry_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: returns 204 and forwards user_id + entry_id to the bridge."""
    calls: dict[str, Any] = {}

    def _fake(session_service: Any, *, app_name: str, user_id: str, entry_id: str) -> str:
        calls.update(user_id=user_id, entry_id=entry_id)
        return entry_id

    monkeypatch.setattr(routes_portfolio, "set_grill_frontier", _fake)
    resp = client.post("/api/experience/e1/grill", headers=_auth_headers())
    assert resp.status_code == 204
    assert calls == {"user_id": _USER_ID, "entry_id": "e1"}


def test_grill_entry_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``None`` bridge return (no session to steer) maps to 404."""
    monkeypatch.setattr(
        routes_portfolio, "set_grill_frontier", lambda *a, **k: None
    )
    resp = client.post("/api/experience/e1/grill", headers=_auth_headers())
    assert resp.status_code == 404


def test_grill_entry_401_without_token(client: TestClient) -> None:
    """Protected: no bearer token → 401."""
    assert client.post("/api/experience/e1/grill").status_code == 401


# ── POST /api/experience/{id}/highlight ───────────────────────────────────────


def test_highlight_entry_204(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: forwards the ``highlighted`` flag from the body to the bridge."""
    calls: dict[str, Any] = {}

    def _fake(
        session_service: Any, *, app_name: str, user_id: str, entry_id: str, highlighted: bool
    ) -> str:
        calls.update(user_id=user_id, entry_id=entry_id, highlighted=highlighted)
        return entry_id

    monkeypatch.setattr(routes_portfolio, "set_entry_highlight", _fake)
    resp = client.post(
        "/api/experience/e2/highlight",
        json={"highlighted": True},
        headers=_auth_headers(),
    )
    assert resp.status_code == 204
    assert calls == {"user_id": _USER_ID, "entry_id": "e2", "highlighted": True}


def test_highlight_entry_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``None`` bridge return (entry not found) maps to 404."""
    monkeypatch.setattr(
        routes_portfolio, "set_entry_highlight", lambda *a, **k: None
    )
    resp = client.post(
        "/api/experience/e2/highlight",
        json={"highlighted": False},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_highlight_entry_422_on_bad_body(client: TestClient) -> None:
    """A malformed body (missing ``highlighted``) yields 422."""
    resp = client.post(
        "/api/experience/e2/highlight", json={}, headers=_auth_headers()
    )
    assert resp.status_code == 422


def test_highlight_entry_401_without_token(client: TestClient) -> None:
    """Protected: no bearer token → 401."""
    resp = client.post("/api/experience/e2/highlight", json={"highlighted": True})
    assert resp.status_code == 401


# ── PATCH /api/experience/{id}/bullet (parity P5) ─────────────────────────────


def test_edit_bullet_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: forwards user_id, entry_id, bullet_index and new_text to the bridge."""
    calls: dict[str, Any] = {}

    def _fake(
        session_service: Any,
        *,
        app_name: str,
        user_id: str,
        entry_id: str,
        bullet_index: int,
        new_text: str,
    ) -> str:
        calls.update(
            user_id=user_id, entry_id=entry_id, bullet_index=bullet_index, new_text=new_text
        )
        return entry_id

    monkeypatch.setattr(routes_portfolio, "update_entry_bullet", _fake)
    resp = client.patch(
        "/api/experience/e3/bullet",
        json={"bullet_index": 1, "new_text": "Cut p99 latency 40%"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 204
    assert calls == {
        "user_id": _USER_ID,
        "entry_id": "e3",
        "bullet_index": 1,
        "new_text": "Cut p99 latency 40%",
    }


def test_edit_bullet_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``None`` bridge return (no session) maps to 404.

    (A missing entry or an out-of-range index is a logged no-op in the bridge that still
    returns the session id → 204.)
    """
    monkeypatch.setattr(routes_portfolio, "update_entry_bullet", lambda *a, **k: None)
    resp = client.patch(
        "/api/experience/e3/bullet",
        json={"bullet_index": 0, "new_text": "x"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_edit_bullet_422_on_bad_body(client: TestClient) -> None:
    """Empty / whitespace-only ``new_text`` and a negative ``bullet_index`` are rejected.

    Whitespace-only matters: the store strips the text and would leave the bullet
    untouched, so accepting it would report 204 for an edit that never happened.
    """
    headers = _auth_headers()
    for body in (
        {"bullet_index": 0, "new_text": ""},
        {"bullet_index": 0, "new_text": "   "},
        {"bullet_index": -1, "new_text": "x"},
    ):
        resp = client.patch("/api/experience/e3/bullet", json=body, headers=headers)
        assert resp.status_code == 422, body


def test_edit_bullet_401_without_token(client: TestClient) -> None:
    resp = client.patch(
        "/api/experience/e3/bullet", json={"bullet_index": 0, "new_text": "x"}
    )
    assert resp.status_code == 401


# ── DELETE /api/story/{id} ────────────────────────────────────────────────────


def test_delete_story_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: returns 204 and forwards user_id + story_id to the bridge."""
    calls: dict[str, Any] = {}

    def _fake(session_service: Any, *, app_name: str, user_id: str, story_id: str) -> str:
        calls.update(user_id=user_id, story_id=story_id)
        return story_id

    monkeypatch.setattr(routes_portfolio, "delete_star_story", _fake)
    resp = client.delete("/api/story/s1", headers=_auth_headers())
    assert resp.status_code == 204
    assert calls == {"user_id": _USER_ID, "story_id": "s1"}


def test_delete_story_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``None`` bridge return (no session) maps to 404.

    (A missing story id is an idempotent no-op that returns the session id → 204;
    the bridge only returns ``None`` when the user has no session at all.)
    """
    monkeypatch.setattr(routes_portfolio, "delete_star_story", lambda *a, **k: None)
    resp = client.delete("/api/story/s1", headers=_auth_headers())
    assert resp.status_code == 404


def test_delete_story_401_without_token(client: TestClient) -> None:
    """Protected: no bearer token → 401."""
    assert client.delete("/api/story/s1").status_code == 401
