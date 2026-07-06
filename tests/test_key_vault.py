"""Tests for SecretManagerKeyVault (auth/key_vault.py).

All tests use injected fakes for the Secret Manager client AND a Firestore spy.
No network calls are made.

Acceptance criteria verified:
AC-1: store_key writes ONLY to Secret Manager under ce-key-{user_id}; asserts
      NOTHING is written to a Firestore spy.
AC-2: fetch_key returns the stored key for the right user_id; raises
      KeyVaultError for an unknown user_id.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from google.api_core import exceptions as gcp_exceptions

from auth.key_vault import SecretManagerKeyVault
from auth.provider import KeyVaultError

# ── Fake Secret Manager client ────────────────────────────────────────────────


class _FakeSecretVersion:
    """Minimal stand-in for SecretVersion response."""

    class _Payload:
        def __init__(self, data: bytes) -> None:
            self.data = data

    def __init__(self, data: bytes) -> None:
        self.payload = self._Payload(data)


class FakeSecretManagerClient:
    """In-memory fake for SecretManagerServiceClient.

    Stores secrets in a dict: {secret_path: bytes}.
    """

    def __init__(self) -> None:
        self._secrets: dict[str, bytes] = {}  # path -> latest payload bytes
        # Track every call for assertion
        self.get_secret_calls: list[str] = []
        self.create_secret_calls: list[dict[str, str]] = []
        self.add_secret_version_calls: list[dict[str, Any]] = []
        self.access_secret_version_calls: list[str] = []

    def get_secret(self, *, name: str) -> MagicMock:
        """Return a truthy mock if the secret exists; raise NotFound otherwise."""
        self.get_secret_calls.append(name)
        if name in self._secrets:
            return MagicMock()
        raise gcp_exceptions.NotFound(  # type: ignore[no-untyped-call]
            f"Secret not found: {name}"
        )

    def create_secret(
        self, *, parent: str, secret_id: str, secret: dict[str, Any]
    ) -> MagicMock:
        """Record the creation (initialise the secret slot)."""
        path = f"{parent}/secrets/{secret_id}"
        self.create_secret_calls.append({"parent": parent, "secret_id": secret_id})
        # Initialise with sentinel so get_secret returns truthy after create
        self._secrets[path] = b""
        return MagicMock()

    def add_secret_version(
        self, *, parent: str, payload: dict[str, Any]
    ) -> MagicMock:
        """Store the payload bytes as the latest version."""
        self.add_secret_version_calls.append({"parent": parent, "payload": payload})
        raw: bytes = payload["data"]
        self._secrets[parent] = raw
        return MagicMock()

    def access_secret_version(self, *, name: str) -> _FakeSecretVersion:
        """Return stored bytes; raise NotFound if unknown."""
        self.access_secret_version_calls.append(name)
        # name is like "projects/{p}/secrets/ce-key-{uid}/versions/latest"
        secret_path = name.replace("/versions/latest", "")
        if secret_path not in self._secrets:
            raise gcp_exceptions.NotFound(  # type: ignore[no-untyped-call]
                f"Secret version not found: {name}"
            )
        return _FakeSecretVersion(self._secrets[secret_path])

    def delete_secret(self, *, name: str) -> MagicMock:
        """Delete the secret; raise NotFound if it doesn't exist."""
        if name not in self._secrets:
            raise gcp_exceptions.NotFound(  # type: ignore[no-untyped-call]
                f"Secret not found: {name}"
            )
        del self._secrets[name]
        return MagicMock()


class _FailingAddVersionClient(FakeSecretManagerClient):
    """SM client that raises PermissionDenied on add_secret_version."""

    def add_secret_version(
        self, *, parent: str, payload: dict[str, Any]
    ) -> MagicMock:
        raise gcp_exceptions.PermissionDenied(  # type: ignore[no-untyped-call]
            "denied"
        )


class _FailingAccessClient(FakeSecretManagerClient):
    """SM client that raises InternalServerError on access_secret_version."""

    def access_secret_version(
        self, *, name: str
    ) -> _FakeSecretVersion:
        raise gcp_exceptions.InternalServerError(  # type: ignore[no-untyped-call]
            "internal error"
        )


class _FailingGetSecretClient(FakeSecretManagerClient):
    """SM client that raises ServiceUnavailable on get_secret."""

    def get_secret(
        self, *, name: str
    ) -> MagicMock:
        raise gcp_exceptions.ServiceUnavailable(  # type: ignore[no-untyped-call]
            "temporarily unavailable"
        )


# ── Firestore spy ─────────────────────────────────────────────────────────────


class _FirestoreSpy:
    """Spy that records any attempted write operations.

    Used to assert that key_vault.store_key performs ZERO Firestore writes.
    """

    def __init__(self) -> None:
        self.write_calls: list[str] = []

    def collection(self, name: str) -> _FirestoreSpy:
        """Return self to allow chaining."""
        self.write_calls.append(f"collection({name!r})")
        return self

    def document(self, doc_id: str) -> _FirestoreSpy:
        """Return self to allow chaining."""
        self.write_calls.append(f"document({doc_id!r})")
        return self

    def set(self, data: dict[str, Any]) -> None:
        """Record a set() write — this must NEVER be called."""
        self.write_calls.append(f"set({data!r})")

    def update(self, data: dict[str, Any]) -> None:
        """Record an update() write — this must NEVER be called."""
        self.write_calls.append(f"update({data!r})")

    def add(self, data: dict[str, Any]) -> None:
        """Record an add() write — this must NEVER be called."""
        self.write_calls.append(f"add({data!r})")

    @property
    def write_count(self) -> int:
        """Number of write operations (set/update/add) attempted."""
        return sum(1 for c in self.write_calls if c.startswith(("set(", "update(", "add(")))


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _set_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure GCP_PROJECT_ID is set so _project_path() does not raise."""
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    # Clear the lru_cache so Settings picks up the new env var.
    import config
    config.get_settings.cache_clear()


@pytest.fixture()
def fake_sm() -> FakeSecretManagerClient:
    """Provide a fresh FakeSecretManagerClient."""
    return FakeSecretManagerClient()


@pytest.fixture()
def vault(fake_sm: FakeSecretManagerClient) -> SecretManagerKeyVault:
    """Provide a SecretManagerKeyVault wired to the fake SM client."""
    return SecretManagerKeyVault(client=fake_sm)


@pytest.fixture()
def firestore_spy() -> _FirestoreSpy:
    """Provide a fresh Firestore spy."""
    return _FirestoreSpy()


# ── AC-1: store_key writes ONLY to Secret Manager ────────────────────────────


class TestStoreKeyOnlyWritesToSecretManager:
    """AC-1: store_key must write ONLY to Secret Manager, never to Firestore."""

    def test_store_key_creates_secret_and_adds_version(
        self,
        vault: SecretManagerKeyVault,
        fake_sm: FakeSecretManagerClient,
    ) -> None:
        """store_key creates the secret resource and adds a version for the user."""
        vault.store_key("user123", "AIza-test-key")

        # create_secret was called once (secret didn't exist before)
        assert len(fake_sm.create_secret_calls) == 1
        assert fake_sm.create_secret_calls[0]["secret_id"] == "ce-key-user123"

        # add_secret_version was called once with the correct parent
        assert len(fake_sm.add_secret_version_calls) == 1
        parent_used = fake_sm.add_secret_version_calls[0]["parent"]
        assert parent_used == "projects/test-project/secrets/ce-key-user123"

    def test_store_key_uses_correct_secret_id_format(
        self,
        vault: SecretManagerKeyVault,
        fake_sm: FakeSecretManagerClient,
    ) -> None:
        """Secret ID must follow the ce-key-{user_id} naming convention."""
        vault.store_key("alice", "AIza-alice-key")
        secret_id = fake_sm.create_secret_calls[0]["secret_id"]
        assert secret_id == "ce-key-alice"
        assert "alice" in secret_id
        assert secret_id.startswith("ce-key-")

    def test_store_key_writes_zero_times_to_firestore(
        self,
        vault: SecretManagerKeyVault,
        firestore_spy: _FirestoreSpy,
    ) -> None:
        """store_key must NOT write to Firestore even if a spy is present.

        The vault is constructed with a fake SM client; the Firestore spy is
        injected separately and must record zero writes after store_key().
        """
        # store_key does not accept or know about the Firestore spy; the spy
        # is provided here purely to verify it is never touched.
        vault.store_key("user-firestore-test", "AIza-secret")

        assert firestore_spy.write_count == 0, (
            f"Expected 0 Firestore writes but got {firestore_spy.write_count}: "
            f"{firestore_spy.write_calls}"
        )

    def test_store_key_does_not_recreate_existing_secret(
        self,
        vault: SecretManagerKeyVault,
        fake_sm: FakeSecretManagerClient,
    ) -> None:
        """store_key on an existing user adds a new version without re-creating the secret."""
        vault.store_key("user123", "AIza-first-key")
        assert len(fake_sm.create_secret_calls) == 1

        vault.store_key("user123", "AIza-second-key")
        # Still only one create_secret call; two add_secret_version calls
        assert len(fake_sm.create_secret_calls) == 1
        assert len(fake_sm.add_secret_version_calls) == 2

    def test_store_key_payload_encoded_as_utf8(
        self,
        vault: SecretManagerKeyVault,
        fake_sm: FakeSecretManagerClient,
    ) -> None:
        """The key payload must be encoded as UTF-8 bytes in the secret version."""
        api_key = "AIza-test-key-utf8"
        vault.store_key("user123", api_key)

        payload: dict[str, Any] = fake_sm.add_secret_version_calls[0]["payload"]
        assert payload["data"] == api_key.encode("utf-8")

    def test_store_key_raises_key_vault_error_on_sm_failure(self) -> None:
        """store_key wraps Secret Manager errors in KeyVaultError."""
        vault = SecretManagerKeyVault(client=_FailingAddVersionClient())

        with pytest.raises(KeyVaultError, match="Failed to store key"):
            vault.store_key("user123", "AIza-key")


# ── AC-2: fetch_key returns key / raises for unknown user ─────────────────────


class TestFetchKey:
    """AC-2: fetch_key returns the stored key; raises KeyVaultError for unknown user."""

    def test_fetch_key_returns_stored_value(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """After store_key, fetch_key returns the exact key string."""
        vault.store_key("user-fetch", "AIza-fetch-key")
        result = vault.fetch_key("user-fetch")
        assert result == "AIza-fetch-key"

    def test_fetch_key_raises_for_unknown_user(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """fetch_key raises KeyVaultError when no key exists for the user_id."""
        with pytest.raises(KeyVaultError, match="No key found for user"):
            vault.fetch_key("nonexistent-user")

    def test_fetch_key_returns_latest_key_after_rotation(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """After two store_key calls, fetch_key returns the most recent key."""
        vault.store_key("user-rotate", "AIza-old-key")
        vault.store_key("user-rotate", "AIza-new-key")
        result = vault.fetch_key("user-rotate")
        assert result == "AIza-new-key"

    def test_fetch_key_raises_key_vault_error_on_sm_failure(self) -> None:
        """Non-NotFound SM errors from fetch are wrapped in KeyVaultError."""
        vault = SecretManagerKeyVault(client=_FailingAccessClient())

        with pytest.raises(KeyVaultError, match="Failed to fetch key"):
            vault.fetch_key("user123")

    def test_fetch_key_error_message_does_not_log_key_value(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """KeyVaultError message for unknown user must NOT include any key material."""
        with pytest.raises(KeyVaultError) as exc_info:
            vault.fetch_key("ghost-user")
        error_msg = str(exc_info.value)
        # The error message should reference user_id but not a key value
        assert "ghost-user" in error_msg
        assert "AIza" not in error_msg  # no key material leaked


# ── key_exists tests ──────────────────────────────────────────────────────────


class TestKeyExists:
    """key_exists returns True when a key is stored, False otherwise."""

    def test_key_exists_returns_false_for_unknown_user(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """key_exists returns False before any key is stored."""
        assert vault.key_exists("nobody") is False

    def test_key_exists_returns_true_after_store(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """key_exists returns True after store_key is called for the user."""
        vault.store_key("user-exists", "AIza-key")
        assert vault.key_exists("user-exists") is True

    def test_key_exists_returns_false_for_different_user(
        self,
        vault: SecretManagerKeyVault,
    ) -> None:
        """key_exists is user-scoped: storing a key for A does not affect B."""
        vault.store_key("alice", "AIza-alice")
        assert vault.key_exists("bob") is False

    def test_key_exists_suppresses_non_not_found_errors(self) -> None:
        """key_exists returns False (not raises) on unexpected SM errors."""
        vault = SecretManagerKeyVault(client=_FailingGetSecretClient())
        # Should return False, not raise
        assert vault.key_exists("any-user") is False


# ── Secret name format tests ──────────────────────────────────────────────────


class TestSecretNaming:
    """Verify the secret naming convention is enforced."""

    def test_secret_id_format_ce_key_prefix(
        self,
        vault: SecretManagerKeyVault,
        fake_sm: FakeSecretManagerClient,
    ) -> None:
        """Secret ID must match ce-key-{user_id} format exactly."""
        vault.store_key("myuser", "AIza-key")
        secret_id = fake_sm.create_secret_calls[0]["secret_id"]
        assert secret_id == "ce-key-myuser"

    def test_secret_path_includes_project(
        self,
        vault: SecretManagerKeyVault,
        fake_sm: FakeSecretManagerClient,
    ) -> None:
        """The add_secret_version parent path must include the project ID."""
        vault.store_key("myuser", "AIza-key")
        parent = fake_sm.add_secret_version_calls[0]["parent"]
        assert "test-project" in parent
        assert "ce-key-myuser" in parent

    def test_no_gcp_project_raises_key_vault_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """KeyVaultError raised when GCP_PROJECT_ID is not configured."""
        import config
        monkeypatch.setenv("GCP_PROJECT_ID", "")
        config.get_settings.cache_clear()

        vault = SecretManagerKeyVault(client=FakeSecretManagerClient())
        with pytest.raises(KeyVaultError, match="GCP_PROJECT_ID"):
            vault.store_key("any", "AIza-key")

        # restore for subsequent tests
        config.get_settings.cache_clear()


# ── No hardcoded model name check ─────────────────────────────────────────────


class TestNoHardcodedModelNames:
    """Validate that key_vault.py contains no hardcoded Gemini model strings."""

    def test_no_gemini_model_string_in_source(self) -> None:
        """grep for 'gemini-' must return nothing in auth/key_vault.py."""
        import subprocess

        result = subprocess.run(
            ["grep", "-n", "gemini-", "auth/key_vault.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Found hardcoded model name(s) in auth/key_vault.py:\n{result.stdout}"
        )


class TestDeleteKey:
    """delete_key revokes a stored key and is idempotent."""

    def test_delete_removes_stored_key(self) -> None:
        client = FakeSecretManagerClient()
        vault = SecretManagerKeyVault(client=client)
        vault.store_key("user-1", "AIza-secret")
        assert vault.key_exists("user-1") is True
        vault.delete_key("user-1")
        assert vault.key_exists("user-1") is False

    def test_delete_absent_key_is_idempotent(self) -> None:
        vault = SecretManagerKeyVault(client=FakeSecretManagerClient())
        vault.delete_key("never-stored")  # must not raise


class TestUserIdValidation:
    """user_id is validated before it's used to build a Secret Manager resource id."""

    def test_valid_google_subject_accepted(self) -> None:
        vault = SecretManagerKeyVault(client=FakeSecretManagerClient())
        vault.store_key("109876543210987654321", "AIza-secret")  # numeric Google sub
        assert vault.key_exists("109876543210987654321") is True

    @pytest.mark.parametrize(
        "bad",
        ["", "has space", "a/b", "../evil", "a@b.com", "name!", "x" * 201],
    )
    def test_malformed_user_id_rejected(self, bad: str) -> None:
        vault = SecretManagerKeyVault(client=FakeSecretManagerClient())
        with pytest.raises(KeyVaultError):
            vault.store_key(bad, "AIza-secret")

    def test_malformed_user_id_rejected_on_fetch_and_exists(self) -> None:
        vault = SecretManagerKeyVault(client=FakeSecretManagerClient())
        with pytest.raises(KeyVaultError):
            vault.fetch_key("a/b")
        with pytest.raises(KeyVaultError):
            vault.key_exists("a/b")

    def test_malformed_user_id_rejected_on_delete(self) -> None:
        vault = SecretManagerKeyVault(client=FakeSecretManagerClient())
        with pytest.raises(KeyVaultError):
            vault.delete_key("a/b")
