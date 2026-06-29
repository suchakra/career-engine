"""CLI authentication via Identity Platform device/loopback OAuth flow.

Provides two distinct paths:
1. **Local dev escape hatch** — if ``settings.dev_user_id`` is set, ``get_user_id()``
   returns it immediately with NO network call.  Intended for fully-offline
   development and CI environments where real auth is unavailable.
2. **Device/loopback OAuth** — a standard OAuth 2.0 device code flow or loopback
   (redirect-URI) flow against Google Identity Platform.  The resulting ID token
   is cached in-process so repeated calls to ``get_user_id()`` are stable without
   extra network round-trips.

Access-mode resolution helper ``resolve_access_mode()`` is also provided here
(not on the interface, but used by the CLI entry-point) so it can be tested
independently.

Design rules:
- No secret (api_key, token payload) is logged anywhere in this module.
- ``get_user_id()`` is idempotent/stable: repeated calls return the same string.
- The token cache is per-instance; a new instance starts fresh.
- All network calls are behind the injected ``_token_fetcher`` callable so tests
  supply a fake without patching globals.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from auth.provider import AuthenticationError, AuthProvider
from config import AccessMode, get_settings

# ── OAuth constants ───────────────────────────────────────────────────────────

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_DEVICE_URL = "https://oauth2.googleapis.com/device/code"
_GOOGLE_CERT_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

# Scopes: openid to get a stable sub claim; email for display only.
_SCOPES = "openid email profile"

# ── Token-info dataclass (lightweight) ───────────────────────────────────────


class _TokenInfo:
    """Lightweight container for a cached OAuth token response.

    Attributes:
        user_id: The stable ``sub`` claim from the ID token.
        id_token: The raw ID token string (kept for re-validation if needed).
        expires_at: Unix timestamp when the token expires.
    """

    __slots__ = ("expires_at", "id_token", "user_id")

    def __init__(self, user_id: str, id_token: str, expires_at: float) -> None:
        """Initialise a token-info container."""
        self.user_id = user_id
        self.id_token = id_token
        self.expires_at = expires_at

    def is_valid(self) -> bool:
        """Return True if the token has not yet expired (with a 60 s grace period)."""
        return time.time() < (self.expires_at - 60)


# ── CliAuthProvider ───────────────────────────────────────────────────────────


class CliAuthProvider(AuthProvider):
    """AuthProvider that resolves a stable user_id for CLI sessions.

    Two operating modes, tried in order:

    1. **Dev escape hatch** — ``settings.dev_user_id`` is non-empty → return it
       directly, no network call, no token cache.
    2. **OAuth device flow** — run a device/loopback OAuth 2.0 exchange against
       Google Identity Platform to obtain an ID token, extract the ``sub`` claim
       as the stable ``user_id``, and cache the token for subsequent calls.

    Args:
        client_id: OAuth 2.0 client ID for Identity Platform.  Defaults to the
            ``GOOGLE_CLIENT_ID`` environment variable via settings; may be passed
            directly for testing.
        token_fetcher: Injectable callable ``(client_id: str, scopes: str) ->
            dict[str, Any]`` that performs the actual device/token exchange.
            Defaults to the built-in loopback helper.  Override in tests to
            avoid network calls.
    """

    def __init__(
        self,
        client_id: str = "",
        token_fetcher: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        """Initialise the CLI auth provider."""
        self._settings = get_settings()
        self._client_id = client_id
        self._token_fetcher: Callable[[str, str], dict[str, Any]] = (
            token_fetcher if token_fetcher is not None else _device_flow_fetch_token
        )
        self._cached_token: _TokenInfo | None = None

    # ── AuthProvider interface ────────────────────────────────────────────────

    def get_user_id(self) -> str:
        """Return a stable, platform-issued user ID for the current principal.

        If the dev escape hatch is active (``settings.dev_user_id`` set), returns
        that value immediately without any network call.

        Otherwise, runs (or re-uses) the cached device/loopback OAuth token and
        extracts the ``sub`` claim, which is the stable Identity Platform UID.

        Returns:
            A non-empty, stable user_id string.

        Raises:
            AuthenticationError: if no valid credential is present and the OAuth
                flow fails.
        """
        # Path 1: dev escape hatch — no network, no token cache
        dev_uid = self._settings.dev_user_id
        if dev_uid:
            return dev_uid

        # Path 2: return cached token if still valid
        if self._cached_token is not None and self._cached_token.is_valid():
            return self._cached_token.user_id

        # Path 3: run the device/loopback flow to acquire a new token
        client_id = self._client_id
        if not client_id:
            raise AuthenticationError(
                "OAuth client_id is not set.  Pass client_id to CliAuthProvider "
                "or set GOOGLE_CLIENT_ID in the environment."
            )

        try:
            token_response = self._token_fetcher(client_id, _SCOPES)
        except Exception as exc:
            raise AuthenticationError(
                f"Device/loopback OAuth flow failed: {exc}"
            ) from exc

        raw_user_id = token_response.get("sub") or token_response.get("user_id", "")
        user_id: str = str(raw_user_id) if raw_user_id else ""
        if not user_id:
            raise AuthenticationError(
                "OAuth token response does not contain a 'sub' claim; "
                "cannot establish a stable user_id."
            )

        id_token = str(token_response.get("id_token", ""))
        expires_in = float(token_response.get("expires_in", 3600))
        expires_at = time.time() + expires_in

        self._cached_token = _TokenInfo(
            user_id=user_id,
            id_token=id_token,
            expires_at=expires_at,
        )
        return user_id

    def is_authenticated(self) -> bool:
        """Return True if the current principal has a valid, non-expired credential.

        For the dev escape hatch, always returns True (the dev user is always
        considered authenticated).  For OAuth, True iff a valid cached token exists.
        """
        if self._settings.dev_user_id:
            return True
        return self._cached_token is not None and self._cached_token.is_valid()


# ── Device/loopback OAuth helper ──────────────────────────────────────────────


def _device_flow_fetch_token(client_id: str, scopes: str) -> dict[str, Any]:
    """Run the Google OAuth 2.0 device authorization flow.

    Step 1: POST to the device-code endpoint to get a ``device_code`` and the
    user-facing ``verification_url`` + ``user_code``.
    Step 2: Print the URL + code for the user to open in a browser.
    Step 3: Poll the token endpoint until the user completes the auth or the
    code expires.

    Args:
        client_id: OAuth 2.0 client ID.
        scopes: Space-separated OAuth scopes string.

    Returns:
        The token-info dict, augmented with the ``sub`` claim extracted from the
        ID token via Google's tokeninfo endpoint.

    Raises:
        AuthenticationError: if the device code request fails, the code expires,
            or the user denies access.
    """
    # Step 1: request a device code
    device_data = urllib.parse.urlencode({"client_id": client_id, "scope": scopes}).encode()
    try:
        with urllib.request.urlopen(_GOOGLE_DEVICE_URL, data=device_data, timeout=15) as resp:
            device_response: dict[str, Any] = json.loads(resp.read().decode())
    except Exception as exc:
        raise AuthenticationError(f"Device code request failed: {exc}") from exc

    device_code = device_response.get("device_code", "")
    user_code = device_response.get("user_code", "")
    verification_url = device_response.get("verification_url", "")
    interval = int(device_response.get("interval", 5))
    expires_in = int(device_response.get("expires_in", 1800))

    # Step 2: prompt the user
    print(
        f"\nOpen the following URL in your browser and enter the code:\n"
        f"  {verification_url}\n"
        f"  Code: {user_code}\n"
    )

    # Step 3: poll for the token
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        poll_data = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            }
        ).encode()
        try:
            with urllib.request.urlopen(_GOOGLE_TOKEN_URL, data=poll_data, timeout=15) as resp:
                token_response: dict[str, Any] = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            error_body: dict[str, Any] = {}
            try:
                error_body = json.loads(exc.read().decode())
            except Exception:
                pass
            error = error_body.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error in ("access_denied", "expired_token"):
                raise AuthenticationError(
                    f"OAuth device flow denied/expired: {error}"
                ) from exc
            raise AuthenticationError(
                f"OAuth token poll failed: {error or exc}"
            ) from exc
        except Exception as exc:
            raise AuthenticationError(f"OAuth token poll failed: {exc}") from exc

        id_token = token_response.get("id_token", "")
        if id_token:
            # Fetch sub claim from tokeninfo; avoids needing a full JWT parser.
            sub = _extract_sub_from_id_token(id_token)
            token_response["sub"] = sub
            token_response["expires_in"] = token_response.get("expires_in", 3600)
            return token_response

    raise AuthenticationError("Device authorization code expired before user completed auth.")


def _extract_sub_from_id_token(id_token: str) -> str:
    """Extract the ``sub`` claim from an ID token using Google's tokeninfo endpoint.

    Uses the tokeninfo API rather than local JWT parsing to avoid a JWT library
    dependency and to validate the token server-side in one step.

    Args:
        id_token: A raw Google-issued ID token string.

    Returns:
        The ``sub`` (subject) claim string.

    Raises:
        AuthenticationError: if the tokeninfo call fails or the token is invalid.
    """
    url = f"{_GOOGLE_CERT_URL}?id_token={urllib.parse.quote(id_token)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            info: dict[str, Any] = json.loads(resp.read().decode())
    except Exception as exc:
        raise AuthenticationError(f"Failed to verify ID token via tokeninfo: {exc}") from exc

    raw_sub = info.get("sub", "")
    sub: str = str(raw_sub) if raw_sub else ""
    if not sub:
        raise AuthenticationError("ID token is missing 'sub' claim.")
    return sub


# ── Access-mode resolution helper ─────────────────────────────────────────────


def resolve_access_mode(user_id: str, key_vault: Any) -> AccessMode:
    """Determine the access mode for a given user.

    Checks whether the user has a stored BYOK key in the vault:
    - Key present → ``AccessMode.BYOK``
    - No key → ``AccessMode.FREE``

    This helper is intentionally kept outside ``CliAuthProvider`` so it can be
    unit-tested independently and reused by other entry points (e.g. Streamlit).

    Args:
        user_id: The platform-issued user identifier.
        key_vault: A ``KeyVault`` instance to check key existence.

    Returns:
        ``AccessMode.BYOK`` if the user has a stored key, ``AccessMode.FREE``
        otherwise.
    """
    if key_vault.key_exists(user_id):
        return AccessMode.BYOK
    return AccessMode.FREE
