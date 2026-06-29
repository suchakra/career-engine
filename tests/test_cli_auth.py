"""Tests for CliAuthProvider (auth/cli_auth.py) and resolve_access_mode.

All tests are network-free: the ``token_fetcher`` and ``key_vault.key_exists``
are injected fakes.

Acceptance criteria verified:
AC-3: AuthProvider.get_user_id() is STABLE across repeated calls for the same identity.
AC-4: The CLI local escape hatch (dev_user_id set) yields a usable user_id with NO
      network call.
AC-5: Access-mode resolution: no user key -> FREE; user key present -> BYOK.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from auth.cli_auth import CliAuthProvider, resolve_access_mode
from auth.provider import AuthenticationError
from config import AccessMode

# ── Helpers / fakes ───────────────────────────────────────────────────────────


def _make_fake_token_fetcher(
    user_id: str = "uid-abc123",
    expires_in: int = 3600,
) -> Any:
    """Return a callable that simulates a successful OAuth token exchange.

    The returned dict matches what the real device flow returns (with the 'sub'
    claim already extracted by ``_extract_sub_from_id_token``).
    """
    call_count = 0

    def _fetcher(client_id: str, scopes: str) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {
            "sub": user_id,
            "id_token": "fake.id.token",
            "access_token": "fake-access-token",
            "expires_in": expires_in,
        }

    _fetcher.call_count_ref = lambda: call_count  # type: ignore[attr-defined]
    return _fetcher


class _FakeKeyVault:
    """Minimal KeyVault fake for access-mode resolution tests."""

    def __init__(self, has_key: bool = False) -> None:
        self._has_key = has_key

    def key_exists(self, user_id: str) -> bool:
        """Return True iff the vault was initialised with has_key=True."""
        return self._has_key

    def store_key(self, user_id: str, api_key: str) -> None:
        """No-op for tests."""
        self._has_key = True

    def fetch_key(self, user_id: str) -> str:
        """Return a dummy key string."""
        return "AIza-fake-key"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure each test starts with a clean settings singleton."""
    import config
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


# ── AC-4: Dev escape hatch — no network call ──────────────────────────────────


class TestDevEscapeHatch:
    """AC-4: When dev_user_id is set, get_user_id() returns it with NO network call."""

    def test_dev_user_id_returned_directly(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """get_user_id() returns dev_user_id without any OAuth/network call."""
        monkeypatch.setenv("DEV_USER_ID", "local-dev-user")
        import config
        config.get_settings.cache_clear()

        network_called = False

        def _should_not_be_called(client_id: str, scopes: str) -> dict[str, Any]:
            nonlocal network_called
            network_called = True
            raise AssertionError("Token fetcher must NOT be called with dev_user_id set")

        provider = CliAuthProvider(
            client_id="fake-client-id",
            token_fetcher=_should_not_be_called,
        )
        result = provider.get_user_id()

        assert result == "local-dev-user", f"Expected 'local-dev-user', got {result!r}"
        assert not network_called, "Token fetcher was called despite dev_user_id being set"

    def test_dev_user_id_is_stable_across_calls(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Repeated get_user_id() calls all return the same dev_user_id."""
        monkeypatch.setenv("DEV_USER_ID", "stable-dev-user")
        import config
        config.get_settings.cache_clear()

        provider = CliAuthProvider(client_id="x")
        ids = [provider.get_user_id() for _ in range(5)]
        assert ids == ["stable-dev-user"] * 5

    def test_dev_user_id_is_authenticated_true(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """is_authenticated() returns True when dev_user_id is set."""
        monkeypatch.setenv("DEV_USER_ID", "dev-user")
        import config
        config.get_settings.cache_clear()

        provider = CliAuthProvider(client_id="x")
        assert provider.is_authenticated() is True

    def test_empty_dev_user_id_falls_through_to_oauth(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An empty (unset) dev_user_id triggers the OAuth path, not the escape hatch."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        fetcher = _make_fake_token_fetcher(user_id="oauth-user")
        provider = CliAuthProvider(client_id="real-client-id", token_fetcher=fetcher)
        result = provider.get_user_id()
        assert result == "oauth-user"


# ── AC-3: get_user_id() is stable ────────────────────────────────────────────


class TestGetUserIdStability:
    """AC-3: get_user_id() is idempotent / stable for the same identity."""

    def test_same_user_id_returned_on_repeated_calls(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Repeated get_user_id() calls return the same user_id without re-fetching."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        fetcher = _make_fake_token_fetcher(user_id="uid-stable-123")
        provider = CliAuthProvider(client_id="client-id", token_fetcher=fetcher)

        ids = [provider.get_user_id() for _ in range(3)]
        assert ids == ["uid-stable-123", "uid-stable-123", "uid-stable-123"]

    def test_token_fetcher_called_only_once_for_multiple_get_user_id_calls(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The OAuth flow is executed once; subsequent calls use the cached token."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        call_count = 0

        def _counting_fetcher(client_id: str, scopes: str) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {
                "sub": "uid-cached",
                "id_token": "tok",
                "expires_in": 3600,
            }

        provider = CliAuthProvider(client_id="cid", token_fetcher=_counting_fetcher)
        for _ in range(5):
            provider.get_user_id()

        assert call_count == 1, (
            f"Token fetcher should be called once; was called {call_count} times"
        )

    def test_is_authenticated_true_after_successful_oauth(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """is_authenticated() returns True after a successful OAuth token fetch."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        fetcher = _make_fake_token_fetcher(user_id="uid-authed")
        provider = CliAuthProvider(client_id="cid", token_fetcher=fetcher)
        provider.get_user_id()  # trigger the flow

        assert provider.is_authenticated() is True

    def test_is_authenticated_false_before_get_user_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """is_authenticated() returns False before any authentication attempt."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        provider = CliAuthProvider(client_id="cid", token_fetcher=_make_fake_token_fetcher())
        assert provider.is_authenticated() is False


# ── Error cases ───────────────────────────────────────────────────────────────


class TestCliAuthErrors:
    """Error handling in CliAuthProvider."""

    def test_raises_authentication_error_when_no_client_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """get_user_id() raises AuthenticationError when client_id is not set."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        provider = CliAuthProvider(client_id="", token_fetcher=_make_fake_token_fetcher())
        with pytest.raises(AuthenticationError, match="client_id"):
            provider.get_user_id()

    def test_raises_authentication_error_when_oauth_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """get_user_id() raises AuthenticationError when the OAuth flow fails."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        def _failing_fetcher(client_id: str, scopes: str) -> dict[str, Any]:
            raise RuntimeError("network error")

        provider = CliAuthProvider(client_id="cid", token_fetcher=_failing_fetcher)
        with pytest.raises(AuthenticationError, match="OAuth flow failed"):
            provider.get_user_id()

    def test_raises_authentication_error_when_sub_missing_from_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """get_user_id() raises AuthenticationError when token lacks 'sub' claim."""
        monkeypatch.setenv("DEV_USER_ID", "")
        import config
        config.get_settings.cache_clear()

        def _no_sub_fetcher(client_id: str, scopes: str) -> dict[str, Any]:
            return {"id_token": "tok", "expires_in": 3600}  # no 'sub'

        provider = CliAuthProvider(client_id="cid", token_fetcher=_no_sub_fetcher)
        with pytest.raises(AuthenticationError, match="'sub' claim"):
            provider.get_user_id()


# ── AC-5: Access-mode resolution ─────────────────────────────────────────────


class TestResolveAccessMode:
    """AC-5: resolve_access_mode returns correct AccessMode based on key presence."""

    def test_no_key_returns_free_mode(self) -> None:
        """resolve_access_mode returns FREE when no key is stored for the user."""
        vault = _FakeKeyVault(has_key=False)
        result = resolve_access_mode("user-no-key", vault)
        assert result == AccessMode.FREE

    def test_key_present_returns_byok_mode(self) -> None:
        """resolve_access_mode returns BYOK when a key is stored for the user."""
        vault = _FakeKeyVault(has_key=True)
        result = resolve_access_mode("user-with-key", vault)
        assert result == AccessMode.BYOK

    def test_free_is_default_when_vault_has_no_key(self) -> None:
        """FREE is the default/safe mode when the vault reports no key."""
        vault = _FakeKeyVault(has_key=False)
        assert resolve_access_mode("fresh-user", vault) == AccessMode.FREE

    def test_byok_after_store_key(self) -> None:
        """After store_key is called on the vault, access mode flips to BYOK."""
        vault = _FakeKeyVault(has_key=False)
        assert resolve_access_mode("user", vault) == AccessMode.FREE
        vault.store_key("user", "AIza-key")
        assert resolve_access_mode("user", vault) == AccessMode.BYOK

    def test_access_mode_free_is_str_enum_value(self) -> None:
        """AccessMode.FREE behaves as a str (serialisable in config/schema)."""
        vault = _FakeKeyVault(has_key=False)
        mode = resolve_access_mode("user", vault)
        assert isinstance(mode, str)
        assert mode == "FREE"

    def test_access_mode_byok_is_str_enum_value(self) -> None:
        """AccessMode.BYOK behaves as a str (serialisable in config/schema)."""
        vault = _FakeKeyVault(has_key=True)
        mode = resolve_access_mode("user", vault)
        assert isinstance(mode, str)
        assert mode == "BYOK"


# ── No hardcoded model name check ─────────────────────────────────────────────


class TestNoHardcodedModelNames:
    """Validate that cli_auth.py contains no hardcoded Gemini model strings."""

    def test_no_gemini_model_string_in_source(self) -> None:
        """grep for 'gemini-' must return nothing in auth/cli_auth.py."""
        import subprocess

        result = subprocess.run(
            ["grep", "-n", "gemini-", "auth/cli_auth.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Found hardcoded model name(s) in auth/cli_auth.py:\n{result.stdout}"
        )
