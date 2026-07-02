"""Firebase / Google Identity Platform AuthProvider for web sessions.

Implements ``AuthProvider`` by verifying a Google-issued ID token (e.g. from the
Identity Platform REST sign-in endpoint) and extracting the stable ``sub`` claim
as the ``user_id``.

For the CLI-first MVP the web token is typically obtained by the browser-facing
layer and passed to this provider as a string; the provider validates it against
Google's public keys (or a supplied verifier for tests).

Design rules:
- No secret or token payload is logged anywhere.
- ``get_user_id()`` is idempotent: repeated calls with the same token return the
  same user_id.
- The token verifier is fully injectable so tests never touch the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

from auth.provider import AuthenticationError, AuthProvider

# Google tokeninfo endpoint — validates and decodes an ID token server-side.
_TOKENINFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

# Issuers Google mints ID tokens under. The tokeninfo endpoint verifies the
# signature but NOT that the token was issued for THIS relying party, so we must
# pin issuer + audience ourselves (see docs/SECURITY.md / set_token).
_DEFAULT_GOOGLE_ISSUERS: frozenset[str] = frozenset(
    {"https://accounts.google.com", "accounts.google.com"}
)


# ── Default verifier (network) ────────────────────────────────────────────────


def google_tokeninfo_verifier(id_token: str) -> dict[str, Any]:
    """Verify an ID token via Google's tokeninfo REST endpoint.

    Returns the decoded claims dict if valid.

    Args:
        id_token: Raw Google-issued ID token string.

    Returns:
        A dict containing at least ``sub``, ``email``, and ``exp`` claims.

    Raises:
        AuthenticationError: if the token is invalid, expired, or the request
            fails.
    """
    url = f"{_TOKENINFO_URL}?id_token={urllib.parse.quote(id_token)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            claims: dict[str, Any] = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        raise AuthenticationError(
            f"Token verification failed (HTTP {exc.code}): {body.decode(errors='replace')}"
        ) from exc
    except Exception as exc:
        raise AuthenticationError(f"Token verification request failed: {exc}") from exc

    if "error_description" in claims or "error" in claims:
        raise AuthenticationError(
            f"Invalid ID token: {claims.get('error_description') or claims.get('error')}"
        )

    sub = claims.get("sub", "")
    if not sub:
        raise AuthenticationError("ID token is missing the 'sub' claim.")
    return claims


# ── FirebaseAuthProvider ──────────────────────────────────────────────────────


class FirebaseAuthProvider(AuthProvider):
    """AuthProvider backed by Google Identity Platform (Firebase Auth).

    Validates a caller-supplied ID token and extracts the stable ``sub`` (UID)
    as the ``user_id``.  The token is re-validated on each new ``set_token()``
    call; subsequent ``get_user_id()`` calls return the cached result until the
    token is replaced.

    Designed for the web/Streamlit path where the frontend obtains a token via
    the Identity Platform SDK and passes it to the backend for verification.

    Args:
        verifier: Optional callable ``(id_token: str) -> dict[str, Any]`` that
            returns decoded JWT claims.  Defaults to the Google tokeninfo REST
            endpoint.  Supply a fake in tests to avoid network calls.
        expected_audiences: The ``aud`` values this application accepts (its
            Identity Platform / Firebase project id, or OAuth client id). When
            ``None`` (the default), it is derived from
            ``settings.firebase_project_id`` (falling back to
            ``settings.gcp_project_id``); if that is also unset, the audience
            check is skipped (dev/test only — production sets a project id).
        allowed_issuers: The ``iss`` values accepted. When ``None`` (default),
            the Google issuers plus ``securetoken.google.com/{project}`` (when a
            project id is known) are used; issuer is ALWAYS enforced.
    """

    def __init__(
        self,
        verifier: Callable[[str], dict[str, Any]] | None = None,
        *,
        expected_audiences: Iterable[str] | None = None,
        allowed_issuers: Iterable[str] | None = None,
    ) -> None:
        """Initialise the Firebase auth provider."""
        self._verifier: Callable[[str], dict[str, Any]] = (
            verifier if verifier is not None else google_tokeninfo_verifier
        )

        # Only touch settings when we must derive a default — a fully-injected
        # provider (both audiences + issuers supplied) stays decoupled from config
        # and its dotenv side effects.
        project = ""
        if expected_audiences is None or allowed_issuers is None:
            from config import get_settings

            settings = get_settings()
            project = settings.firebase_project_id or settings.gcp_project_id

        if expected_audiences is None:
            self._expected_audiences: frozenset[str] = (
                frozenset({project}) if project else frozenset()
            )
        else:
            self._expected_audiences = frozenset(expected_audiences)

        if allowed_issuers is None:
            issuers = set(_DEFAULT_GOOGLE_ISSUERS)
            if project:
                issuers.add(f"https://securetoken.google.com/{project}")
            self._allowed_issuers: frozenset[str] = frozenset(issuers)
        else:
            self._allowed_issuers = frozenset(allowed_issuers)

        self._user_id: str = ""
        self._claims: dict[str, Any] = {}
        self._authenticated: bool = False

    def set_token(self, id_token: str) -> None:
        """Validate an ID token and cache the resulting user_id.

        Must be called before ``get_user_id()``.  Re-calling with a new token
        (e.g. after expiry) replaces the cached identity.

        Args:
            id_token: Raw Identity Platform / Firebase ID token string.

        Raises:
            AuthenticationError: if the token is invalid or verification fails.
        """
        # Reset state before attempting to validate.
        self._authenticated = False
        self._user_id = ""
        self._claims = {}

        claims = self._verifier(id_token)
        sub = claims.get("sub", "")
        if not sub:
            raise AuthenticationError(
                "Verified token does not contain a 'sub' claim; cannot resolve user_id."
            )

        # The tokeninfo endpoint proves the token is genuinely Google-signed and
        # unexpired, but NOT that it was minted for THIS application. Without an
        # audience/issuer check any valid Google/Firebase ID token — including one
        # issued for an unrelated project or OAuth client — would be accepted and
        # its `sub` trusted as our user_id (confused-deputy / token substitution).
        if self._expected_audiences:
            aud = claims.get("aud", "")
            if aud not in self._expected_audiences:
                raise AuthenticationError(
                    "ID token audience is not accepted by this application."
                )

        iss = claims.get("iss", "")
        if iss not in self._allowed_issuers:
            raise AuthenticationError("ID token issuer is not trusted.")

        self._user_id = sub
        self._claims = claims
        self._authenticated = True

    # ── AuthProvider interface ────────────────────────────────────────────────

    def get_user_id(self) -> str:
        """Return the stable Identity Platform user UID (the ``sub`` claim).

        Must call ``set_token()`` first to establish an identity.

        Returns:
            The stable user_id string derived from the verified token's ``sub``
            claim.

        Raises:
            AuthenticationError: if no token has been set or the token has been
                invalidated.
        """
        if not self._authenticated or not self._user_id:
            raise AuthenticationError(
                "No authenticated session.  Call set_token(id_token) first."
            )
        return self._user_id

    def is_authenticated(self) -> bool:
        """Return True if a valid, verified ID token has been set."""
        return self._authenticated and bool(self._user_id)

    # ── Convenience access ────────────────────────────────────────────────────

    @property
    def claims(self) -> dict[str, Any]:
        """Return the full claims dict from the last verified token.

        Useful for display purposes (e.g. email for the UI).  Returns an empty
        dict if not authenticated.

        Note: Do not log or persist this dict in Firestore — it may contain
        user-identifying information that should stay in memory only.
        """
        return dict(self._claims)  # defensive copy
