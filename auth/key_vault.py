"""Secret Manager-backed KeyVault implementation.

Stores and retrieves a user's BYOK Gemini API key exclusively in Google Cloud
Secret Manager.  The key is NEVER written to Firestore and NEVER logged.

Secret naming convention: ce-key-{user_id}
Secret resource path: projects/{gcp_project_id}/secrets/ce-key-{user_id}

Design rules (enforced by tests):
- store_key creates or updates a secret version in Secret Manager only.
- fetch_key reads the latest version of the secret; raises KeyVaultError when
  the secret does not exist.
- key_exists checks for the secret's existence without raising.
- The GCP client is injected (default: get_secret_manager_client()) so tests
  can supply a fake/spy without any network activity.
"""

from __future__ import annotations

import re
from typing import Any

from google.api_core import exceptions as gcp_exceptions

from auth.provider import KeyVault, KeyVaultError
from config import get_secret_manager_client, get_settings

# Secret Manager secret ids must match [A-Za-z0-9_-] (max 255 chars total). The
# user_id is the OIDC ``sub`` (Google issues a numeric subject), but validate it
# defensively so a malformed/hostile subject can never produce an unexpected or
# path-like secret id — the value is used to build a cloud resource name.
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


class SecretManagerKeyVault(KeyVault):
    """KeyVault backed by Google Cloud Secret Manager.

    Keys are stored as secret versions under the secret id ``ce-key-{user_id}``
    in the project defined by ``settings.gcp_project_id``.  The raw API key
    is encrypted at rest by Secret Manager; it is never written to Firestore
    and never surfaced in application logs.

    Args:
        client: Optional Secret Manager service client.  Pass a fake/mock in
            tests to avoid any network calls.  Defaults to the project-level
            factory ``get_secret_manager_client()``.
    """

    def __init__(self, client: Any = None) -> None:
        """Initialise the vault, optionally with an injected client."""
        self._client: Any = client if client is not None else get_secret_manager_client()
        self._settings = get_settings()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _project_path(self) -> str:
        """Return the Secret Manager project path string."""
        project = self._settings.gcp_project_id
        if not project:
            raise KeyVaultError("GCP_PROJECT_ID must be set to use SecretManagerKeyVault.")
        return f"projects/{project}"

    def _secret_id(self, user_id: str) -> str:
        """Return the secret resource ID (not the full path) for a user.

        Raises:
            KeyVaultError: if ``user_id`` isn't a safe secret-id component
                (``[A-Za-z0-9_-]``, 1-200 chars) — belt-and-braces against a
                malformed OIDC subject producing an unexpected resource name.
        """
        if not _USER_ID_RE.fullmatch(user_id):
            raise KeyVaultError(
                "Invalid user_id for secret naming: expected 1-200 chars of [A-Za-z0-9_-]."
            )
        return f"ce-key-{user_id}"

    def _secret_path(self, user_id: str) -> str:
        """Return the full Secret Manager resource path for a user's secret."""
        return f"{self._project_path()}/secrets/{self._secret_id(user_id)}"

    def _secret_version_path(self, user_id: str) -> str:
        """Return the fully-qualified path to the latest version of a secret."""
        return f"{self._secret_path(user_id)}/versions/latest"

    # ── KeyVault interface ────────────────────────────────────────────────────

    def store_key(self, user_id: str, api_key: str) -> None:
        """Encrypt and store the user's Gemini API key in Secret Manager.

        Creates the secret resource if it does not yet exist, then adds a new
        secret version containing the key bytes.  The key is written ONLY to
        Secret Manager — never to Firestore, never to logs.

        Args:
            user_id: The platform-issued user identifier.
            api_key: The raw Gemini API key.

        Raises:
            KeyVaultError: if the project ID is unset or the write fails.
        """
        project_path = self._project_path()
        secret_id = self._secret_id(user_id)
        secret_path = self._secret_path(user_id)

        # Ensure the secret resource exists; create it if not.
        try:
            self._client.get_secret(name=secret_path)
        except gcp_exceptions.NotFound:
            try:
                self._client.create_secret(
                    parent=project_path,
                    secret_id=secret_id,
                    secret={"replication": {"automatic": {}}},
                )
            except gcp_exceptions.GoogleAPICallError as exc:
                raise KeyVaultError(
                    f"Failed to create secret for user {user_id!r}: {exc}"
                ) from exc
        except gcp_exceptions.GoogleAPICallError as exc:
            raise KeyVaultError(
                f"Failed to check secret existence for user {user_id!r}: {exc}"
            ) from exc

        # Add a new version with the key payload.
        try:
            self._client.add_secret_version(
                parent=secret_path,
                payload={"data": api_key.encode("utf-8")},
            )
        except gcp_exceptions.GoogleAPICallError as exc:
            raise KeyVaultError(
                f"Failed to store key for user {user_id!r}: {exc}"
            ) from exc

    def fetch_key(self, user_id: str) -> str:
        """Retrieve the user's Gemini API key from Secret Manager.

        Args:
            user_id: The platform-issued user identifier.

        Returns:
            The raw API key string decoded from the secret payload.

        Raises:
            KeyVaultError: if the secret does not exist or the read fails.
        """
        version_path = self._secret_version_path(user_id)
        try:
            response = self._client.access_secret_version(name=version_path)
            raw: bytes = response.payload.data
            return raw.decode("utf-8")
        except gcp_exceptions.NotFound as exc:
            raise KeyVaultError(
                f"No key found for user {user_id!r}. "
                "Store a key first via store_key()."
            ) from exc
        except gcp_exceptions.GoogleAPICallError as exc:
            raise KeyVaultError(
                f"Failed to fetch key for user {user_id!r}: {exc}"
            ) from exc

    def key_exists(self, user_id: str) -> bool:
        """Return True if a key is stored for the given user_id.

        Uses a lightweight get_secret call rather than accessing the secret
        payload; no key material is transmitted.

        Args:
            user_id: The platform-issued user identifier.

        Returns:
            True if the secret resource exists, False otherwise.
        """
        try:
            self._client.get_secret(name=self._secret_path(user_id))
            return True
        except gcp_exceptions.NotFound:
            return False
        except gcp_exceptions.GoogleAPICallError:
            # Treat any non-NotFound error as "unknown" to be safe; callers
            # that need strict failure propagation should use fetch_key.
            return False

    def delete_key(self, user_id: str) -> None:
        """Delete the user's stored key (revoke). Idempotent — no error if absent.

        Args:
            user_id: The platform-issued user identifier.

        Raises:
            KeyVaultError: if the delete fails for a reason other than "not found".
        """
        try:
            self._client.delete_secret(name=self._secret_path(user_id))
        except gcp_exceptions.NotFound:
            return  # already gone — revoke is idempotent
        except gcp_exceptions.GoogleAPICallError as exc:
            raise KeyVaultError(
                f"Failed to delete key for user {user_id!r}: {exc}"
            ) from exc
