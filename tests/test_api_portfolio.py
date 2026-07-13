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
from schema import (
    Bullet,
    BulletSource,
    CareerEngineState,
    Entry,
    ExperienceType,
    StarStory,
)
from web.portfolio_store import AddedBullet

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


# ── POST /api/experience/{id}/bullet — append a bullet ────────────────────────


def test_add_bullet_201_returns_the_new_bullet_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: forwards the text to the bridge and RETURNS the new bullet's id.

    The id is not a nicety (CQ-6b): a client that overwrote a story-derived résumé line must
    re-identify that line as the bullet it just created, or its next edit tries to create a
    second bullet for the same story and is refused.
    """
    calls: dict[str, Any] = {}

    def _fake(
        session_service: Any,
        *,
        app_name: str,
        user_id: str,
        entry_id: str,
        text: str,
        derived_from_story_id: str = "",
    ) -> AddedBullet:
        calls.update(user_id=user_id, entry_id=entry_id, text=text)
        return AddedBullet("sid", "b-99")

    monkeypatch.setattr(routes_portfolio, "add_entry_bullet", _fake)
    resp = client.post(
        "/api/experience/e4/bullet",
        json={"text": "Shipped billing v2"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201
    assert resp.json() == {"bullet_id": "b-99"}
    assert calls == {"user_id": _USER_ID, "entry_id": "e4", "text": "Shipped billing v2"}


def test_add_bullet_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``None`` bridge return (no session) maps to 404."""
    monkeypatch.setattr(routes_portfolio, "add_entry_bullet", lambda *a, **k: None)
    resp = client.post(
        "/api/experience/e4/bullet", json={"text": "x"}, headers=_auth_headers()
    )
    assert resp.status_code == 404


def test_add_bullet_422_on_blank_text(client: TestClient) -> None:
    """Empty / whitespace-only text is rejected (the store would drop it silently)."""
    for text in ("", "   "):
        resp = client.post(
            "/api/experience/e4/bullet", json={"text": text}, headers=_auth_headers()
        )
        assert resp.status_code == 422, text


def test_add_bullet_401_without_token(client: TestClient) -> None:
    assert client.post("/api/experience/e4/bullet", json={"text": "x"}).status_code == 401


# ── CQ-6b: overwriting a story-derived line ──────────────────────────────────


def _state_with_a_story(*, validated: bool = True) -> tuple[CareerEngineState, Entry, StarStory]:
    entry = Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme")
    story = StarStory(
        entry_id=str(entry.entry_id), pillar="delivery",
        result="Cut deploy failures 40%", metrics_validated=validated,
    )
    return (
        CareerEngineState(work_timeline=[entry], extracted_star_stories=[story]),
        entry,
        story,
    )


def _fake_load(state: CareerEngineState) -> Any:
    async def _load(*a: Any, **k: Any) -> CareerEngineState:
        return state

    return _load


def test_overwriting_a_story_line_persists_a_bullet_that_SPEAKS_FOR_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole destination. Without the link the POST is an orphan bullet: the story keeps
    rendering its raw grill text and the résumé gains a DUPLICATE."""
    state, entry, story = _state_with_a_story()
    calls: dict[str, Any] = {}

    def _fake(session_service: Any, **kw: Any) -> AddedBullet:
        calls.update(kw)
        return AddedBullet("sid", "b-1")

    monkeypatch.setattr(routes_portfolio, "atry_load_latest_discovery_state", _fake_load(state))
    monkeypatch.setattr(routes_portfolio, "add_entry_bullet", _fake)

    resp = client.post(
        f"/api/experience/{entry.entry_id}/bullet",
        json={"text": "Rebuilt CI, cutting deploy failures 40%",
              "derived_from_story_id": str(story.story_id)},
        headers=_auth_headers(),
    )

    assert resp.status_code == 201
    assert calls["derived_from_story_id"] == str(story.story_id)


def test_a_story_on_ANOTHER_entry_is_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cross-entry link would let a bullet borrow a metric it never earned."""
    state, _entry, story = _state_with_a_story()
    other = Entry(type=ExperienceType.FULL_TIME, title="Lead", org="BitCrafty")
    state = state.model_copy(update={"work_timeline": [*state.work_timeline, other]})
    monkeypatch.setattr(routes_portfolio, "atry_load_latest_discovery_state", _fake_load(state))

    resp = client.post(
        f"/api/experience/{other.entry_id}/bullet",
        json={"text": "x", "derived_from_story_id": str(story.story_id)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_an_UNVALIDATED_story_is_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The link BORROWS the story's metric — so the story must actually have one.

    Otherwise a bullet is born marked-as-covered without ever having been grilled: the false
    QUANTIFIED that AD-18.5 calls the worst error coverage can make.
    """
    state, entry, story = _state_with_a_story(validated=False)
    monkeypatch.setattr(routes_portfolio, "atry_load_latest_discovery_state", _fake_load(state))

    resp = client.post(
        f"/api/experience/{entry.entry_id}/bullet",
        json={"text": "x", "derived_from_story_id": str(story.story_id)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_a_SECOND_bullet_for_the_same_story_is_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale preview: someone polished this line elsewhere while the tab was open.

    Minting a second bullet claiming the same story would put the achievement on the résumé
    twice. The client is told to reload rather than silently duplicating it.
    """
    state, entry, story = _state_with_a_story()
    entry.bullets = [
        Bullet(text="Rebuilt CI, cutting failures 40%", source=BulletSource.GRILLED,
               derived_from_story_id=str(story.story_id))
    ]
    monkeypatch.setattr(routes_portfolio, "atry_load_latest_discovery_state", _fake_load(state))

    resp = client.post(
        f"/api/experience/{entry.entry_id}/bullet",
        json={"text": "Something else", "derived_from_story_id": str(story.story_id)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 409


def test_the_EDIT_route_cannot_set_the_story_link(client: TestClient) -> None:
    """The link is settable only at CREATION (schema.py).

    If an edit could set it, a client could point an UNTOUCHED, ungrilled bullet at any
    validated story on the entry and have it marked covered — burying work the user still
    owes. The strict DTO rejects the field outright.
    """
    resp = client.patch(
        "/api/experience/e4/bullet",
        json={"bullet_id": "b1", "new_text": "x", "derived_from_story_id": "s1"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


# ── PATCH /api/experience/{id}/bullet (parity P5) ─────────────────────────────


def test_edit_bullet_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: forwards user_id, entry_id, bullet_id and new_text to the bridge."""
    calls: dict[str, Any] = {}

    def _fake(
        session_service: Any,
        *,
        app_name: str,
        user_id: str,
        entry_id: str,
        bullet_id: str,
        new_text: str,
    ) -> str:
        calls.update(
            user_id=user_id, entry_id=entry_id, bullet_id=bullet_id, new_text=new_text
        )
        return entry_id

    monkeypatch.setattr(routes_portfolio, "update_entry_bullet", _fake)
    resp = client.patch(
        "/api/experience/e3/bullet",
        json={"bullet_id": "b-1", "new_text": "Cut p99 latency 40%"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 204
    assert calls == {
        "user_id": _USER_ID,
        "entry_id": "e3",
        "bullet_id": "b-1",
        "new_text": "Cut p99 latency 40%",
    }


def test_edit_bullet_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``None`` bridge return (no session) maps to 404.

    (A missing entry or an unknown ``bullet_id`` is a logged no-op in the bridge that
    still returns the session id → 204.)
    """
    monkeypatch.setattr(routes_portfolio, "update_entry_bullet", lambda *a, **k: None)
    resp = client.patch(
        "/api/experience/e3/bullet",
        json={"bullet_id": "b-1", "new_text": "x"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_edit_bullet_422_on_bad_body(client: TestClient) -> None:
    """Empty / whitespace-only ``new_text``, and an empty ``bullet_id``, are rejected.

    Whitespace-only text matters: the store strips it and would leave the bullet
    untouched, so accepting it would report 204 for an edit that never happened. An empty
    ``bullet_id`` addresses no bullet at all.
    """
    headers = _auth_headers()
    for body in (
        {"bullet_id": "b-1", "new_text": ""},
        {"bullet_id": "b-1", "new_text": "   "},
        {"bullet_id": "", "new_text": "x"},  # an empty bullet_id addresses nothing
    ):
        resp = client.patch("/api/experience/e3/bullet", json=body, headers=headers)
        assert resp.status_code == 422, body


def test_edit_bullet_401_without_token(client: TestClient) -> None:
    resp = client.patch(
        "/api/experience/e3/bullet", json={"bullet_id": "b-1", "new_text": "x"}
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


# ── DELETE bullet / entry (CQ-3) ──────────────────────────────────────────────


def test_remove_bullet_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: forwards user_id, entry_id and bullet_id to the bridge."""
    calls: dict[str, Any] = {}

    def _fake(
        session_service: Any, *, app_name: str, user_id: str, entry_id: str, bullet_id: str
    ) -> str:
        calls.update(user_id=user_id, entry_id=entry_id, bullet_id=bullet_id)
        return entry_id

    monkeypatch.setattr(routes_portfolio, "delete_entry_bullet", _fake)
    resp = client.delete("/api/experience/e5/bullet/b-9", headers=_auth_headers())

    assert resp.status_code == 204
    assert calls == {"user_id": _USER_ID, "entry_id": "e5", "bullet_id": "b-9"}


def test_remove_bullet_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_portfolio, "delete_entry_bullet", lambda *a, **k: None)
    resp = client.delete("/api/experience/e5/bullet/b-9", headers=_auth_headers())
    assert resp.status_code == 404


def test_remove_bullet_401_without_token(client: TestClient) -> None:
    assert client.delete("/api/experience/e5/bullet/b-9").status_code == 401


def test_remove_entry_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: forwards user_id + entry_id (the store cascades to its stories)."""
    calls: dict[str, Any] = {}

    def _fake(session_service: Any, *, app_name: str, user_id: str, entry_id: str) -> str:
        calls.update(user_id=user_id, entry_id=entry_id)
        return entry_id

    monkeypatch.setattr(routes_portfolio, "delete_entry", _fake)
    resp = client.delete("/api/experience/e5", headers=_auth_headers())

    assert resp.status_code == 204
    assert calls == {"user_id": _USER_ID, "entry_id": "e5"}


def test_remove_entry_404_when_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_portfolio, "delete_entry", lambda *a, **k: None)
    assert client.delete("/api/experience/e5", headers=_auth_headers()).status_code == 404


def test_remove_entry_401_without_token(client: TestClient) -> None:
    assert client.delete("/api/experience/e5").status_code == 401


def test_accept_bullets_422_on_a_malformed_source_id(client: TestClient) -> None:
    """A malformed source_id must be a 422, not a 500.

    source_id comes from the CLIENT; `UUID("not-a-uuid")` raises ValueError, which would
    surface as an unhandled 500.
    """
    resp = client.post(
        "/api/experience/e9/bullets/accept",
        json={"accepted": [{"source_id": "bullet:not-a-uuid", "text": "x"}]},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422
