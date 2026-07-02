"""Tests for jobs/sweep_endpoint.py — the OIDC-authenticated sweep HTTP handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jobs.sweep_endpoint import SweepHttpResponse, handle_sweep_request
from schema import UserWorkspace

_AUD = "https://career-engine-abc-uc.a.run.app"


class _FakeStore:
    """Minimal in-memory WorkspaceStore for the sweep."""

    def __init__(self, workspaces: dict[str, UserWorkspace] | None = None) -> None:
        self._w = workspaces or {}

    def list_user_ids(self) -> list[str]:
        return list(self._w)

    def load(self, user_id: str) -> UserWorkspace:
        return self._w.get(user_id, UserWorkspace())

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        self._w[user_id] = workspace


def _verifier(claims: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    def _v(_token: str) -> dict[str, Any]:
        return claims

    return _v


def _raising_verifier(_token: str) -> dict[str, Any]:
    raise ValueError("bad signature")


def _call(authorization: str | None, **kw: Any) -> SweepHttpResponse:
    defaults: dict[str, Any] = {
        "store": _FakeStore(),
        "today": "2026-07-02",
        "expected_audiences": {_AUD},
        "verifier": _verifier({"aud": _AUD, "email": "sched@proj.iam.gserviceaccount.com"}),
        "log": lambda _m: None,
    }
    defaults.update(kw)
    return handle_sweep_request(authorization=authorization, **defaults)


class TestAuthGuards:
    def test_missing_header_is_401(self) -> None:
        assert _call(None).status == 401

    def test_malformed_header_is_401(self) -> None:
        assert _call("Token abc").status == 401
        assert _call("Bearer").status == 401
        assert _call("Bearer   ").status == 401

    def test_bad_token_is_401(self) -> None:
        assert _call("Bearer x", verifier=_raising_verifier).status == 401

    def test_wrong_audience_is_403(self) -> None:
        resp = _call("Bearer x", verifier=_verifier({"aud": "https://evil.example"}))
        assert resp.status == 403

    def test_unconfigured_audience_is_rejected(self) -> None:
        # Secure-by-default: no expected audience → reject even a valid signature.
        resp = _call("Bearer x", expected_audiences=set())
        assert resp.status == 403

    def test_wrong_service_account_is_403(self) -> None:
        resp = _call(
            "Bearer x",
            verifier=_verifier({"aud": _AUD, "email": "attacker@evil.iam.gserviceaccount.com"}),
            allowed_service_accounts={"sched@proj.iam.gserviceaccount.com"},
        )
        assert resp.status == 403


class TestSuccess:
    def test_valid_token_runs_sweep_and_returns_report(self) -> None:
        resp = _call("Bearer good")
        assert resp.status == 200
        assert set(resp.body) == {
            "users_processed",
            "users_failed",
            "pending_actions_created",
        }
        assert resp.body["users_processed"] == 0  # empty store

    def test_allowed_service_account_passes(self) -> None:
        resp = _call(
            "Bearer good",
            allowed_service_accounts={"sched@proj.iam.gserviceaccount.com"},
        )
        assert resp.status == 200
