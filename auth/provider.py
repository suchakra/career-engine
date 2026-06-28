"""AuthProvider and KeyVault abstract interfaces.

Phase 0 — interface definitions only.  No live network calls, no GCP SDK
calls.  Phase 1 (WS-D) provides the concrete implementations:
  - auth/cli_auth.py  → device/loopback OAuth + local escape hatch
  - auth/firebase_auth.py → Identity Platform web
  - auth/key_vault.py → Secret Manager BYOK key store/fetch

Design rules:
- AuthProvider returns a stable user_id (never a raw API key).
- KeyVault stores and fetches the user's BYOK Gemini key from Secret Manager.
  The key is NEVER written to Firestore; a test in WS-D must assert this.
- Secret name format: ce-key-{user_id}  (see config.secret_name_for_user).
- No method here performs I/O; all I/O is in the concrete implementations.

ADK 2.0 note:
    google.adk.auth exposes AuthConfig, AuthCredential, and BaseAuthProvider
    for tool-level OAuth flows.  Those are orthogonal to *application* identity
    managed here.  CareerEngine uses Identity Platform for user identity, not
    the ADK credential subsystem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AuthProvider(ABC):
    """Abstract interface for resolving a stable user identity.

    Concrete implementations: cli_auth.CliAuthProvider, firebase_auth.FirebaseAuthProvider.
    """

    @abstractmethod
    def get_user_id(self) -> str:
        """Return a stable, platform-issued user ID for the current principal.

        Must be idempotent: repeated calls for the same authenticated principal
        return the same user_id string.

        Raises:
            AuthenticationError: if no valid credential is present.
        """
        ...

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Return True if the current principal has a valid, non-expired credential."""
        ...


class KeyVault(ABC):
    """Abstract interface for storing and retrieving a user's BYOK Gemini key.

    Keys are stored in Secret Manager under the name ce-key-{user_id}.
    The key is NEVER written to Firestore or logged.
    """

    @abstractmethod
    def store_key(self, user_id: str, api_key: str) -> None:
        """Encrypt and store the user's Gemini API key in Secret Manager.

        Args:
            user_id: The platform-issued user identifier.
            api_key: The raw Gemini API key.  Stored encrypted at rest by
                Secret Manager; never logged, never written to Firestore.

        Raises:
            KeyVaultError: if the key cannot be stored.
        """
        ...

    @abstractmethod
    def fetch_key(self, user_id: str) -> str:
        """Retrieve the user's Gemini API key from Secret Manager.

        Args:
            user_id: The platform-issued user identifier.

        Returns:
            The raw API key string.

        Raises:
            KeyVaultError: if the key does not exist or cannot be fetched.
        """
        ...

    @abstractmethod
    def key_exists(self, user_id: str) -> bool:
        """Return True if a key is stored for the given user_id."""
        ...


# ── Domain exceptions ─────────────────────────────────────────────────────────


class AuthenticationError(Exception):
    """Raised when authentication fails or no credential is present."""


class KeyVaultError(Exception):
    """Raised when a Secret Manager key operation fails."""
