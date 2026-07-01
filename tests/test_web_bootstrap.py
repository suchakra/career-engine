"""Tests for web auth + session bootstrap (Phase 2B).

The auth provider and workspace store are faked (no network, no Firestore).
Covers: authenticated bootstrap loads the namespaced workspace, unauthenticated
paths are rejected safely, and no secret material rides on the WebSession.
"""

from __future__ import annotations

import json

import pytest

from auth.provider import AuthenticationError
from schema import Application, UserWorkspace
from web.bootstrap import (
    WebSession,
    bootstrap_web_session,
    try_bootstrap_web_session,
)


class _FakeAuth:
    """Fake AuthProvider: maps a fixed 'good' token to a stable user_id."""

    def __init__(self, *, good_token: str = "good", user_id: str = "uid-123") -> None:
        self._good = good_token
        self._uid = user_id
        self._current = ""

    def set_token(self, id_token: str) -> None:
        if id_token != self._good:
            raise AuthenticationError("bad token")
        self._current = self._uid

    def get_user_id(self) -> str:
        if not self._current:
            raise AuthenticationError("no session")
        return self._current


class _FakeStore:
    """Fake workspace store returning a per-user workspace."""

    def __init__(self, workspaces: dict[str, UserWorkspace] | None = None) -> None:
        self._ws = workspaces or {}

    def load(self, user_id: str) -> UserWorkspace:
        return self._ws.get(user_id, UserWorkspace())


class TestBootstrap:
    """bootstrap_web_session verifies token → loads the namespaced workspace."""

    def test_authenticated_loads_workspace(self) -> None:
        """A valid token resolves the user_id and loads that user's workspace."""
        ws = UserWorkspace(applications=[Application(company="Acme")])
        session = bootstrap_web_session(
            id_token="good",
            auth_provider=_FakeAuth(),
            workspace_store=_FakeStore({"uid-123": ws}),
        )
        assert isinstance(session, WebSession)
        assert session.user_id == "uid-123"
        assert session.workspace == ws

    def test_stable_user_id_maps_to_namespace(self) -> None:
        """The same identity resolves to the same user_id (namespace key)."""
        auth = _FakeAuth()
        s1 = bootstrap_web_session(id_token="good", auth_provider=auth, workspace_store=_FakeStore())
        s2 = bootstrap_web_session(id_token="good", auth_provider=auth, workspace_store=_FakeStore())
        assert s1.user_id == s2.user_id == "uid-123"

    def test_invalid_token_raises(self) -> None:
        """An invalid token raises AuthenticationError."""
        with pytest.raises(AuthenticationError):
            bootstrap_web_session(
                id_token="bad", auth_provider=_FakeAuth(), workspace_store=_FakeStore()
            )

    def test_empty_token_raises(self) -> None:
        """An empty token raises AuthenticationError (no partial state)."""
        with pytest.raises(AuthenticationError):
            bootstrap_web_session(
                id_token="", auth_provider=_FakeAuth(), workspace_store=_FakeStore()
            )

    def test_no_secret_material_on_session(self) -> None:
        """The WebSession payload carries no secret-like fields."""
        session = bootstrap_web_session(
            id_token="good", auth_provider=_FakeAuth(), workspace_store=_FakeStore()
        )
        blob = json.dumps(
            {"user_id": session.user_id, "workspace": session.workspace.model_dump(mode="json")}
        )
        for forbidden in ("api_key", "token", "password", "secret", "credential"):
            assert forbidden not in blob


class TestTryBootstrap:
    """try_bootstrap_web_session gives the UX layer a safe non-raising path."""

    def test_none_token_returns_none(self) -> None:
        """No token → None (render a sign-in prompt), not an exception."""
        assert (
            try_bootstrap_web_session(
                id_token=None, auth_provider=_FakeAuth(), workspace_store=_FakeStore()
            )
            is None
        )

    def test_bad_token_returns_none(self) -> None:
        """A bad token → None rather than a crash."""
        assert (
            try_bootstrap_web_session(
                id_token="bad", auth_provider=_FakeAuth(), workspace_store=_FakeStore()
            )
            is None
        )

    def test_good_token_returns_session(self) -> None:
        """A good token returns a populated WebSession."""
        session = try_bootstrap_web_session(
            id_token="good", auth_provider=_FakeAuth(), workspace_store=_FakeStore()
        )
        assert session is not None
        assert session.user_id == "uid-123"

    def test_non_auth_load_failure_returns_none_no_leak(self) -> None:
        """A non-auth error from the workspace load (e.g. version mismatch) → None, not a crash."""
        from database.firestore_session import ContractVersionError

        class _BadStore:
            def load(self, user_id: str) -> UserWorkspace:
                raise ContractVersionError("stored=99.0.0")

        result = try_bootstrap_web_session(
            id_token="good", auth_provider=_FakeAuth(), workspace_store=_BadStore()
        )
        assert result is None
