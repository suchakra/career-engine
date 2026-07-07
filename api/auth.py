"""Bearer-token → ``user_id`` trust boundary for the API.

The single place the transport layer converts an ``Authorization: Bearer
<id_token>`` header into a verified, stable ``user_id``. Verification is
delegated to the existing :class:`~auth.firebase_auth.FirebaseAuthProvider`
(AD-16.4), so this module builds no new cookie/OIDC/session machinery.

Security rules (see docs/SECURITY.md):
- The raw token and the decoded claims are NEVER logged or persisted.
- Any verification failure surfaces as a 401 with an opaque ``detail`` — never
  a stack trace and never the token itself.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from auth.firebase_auth import FirebaseAuthProvider
from auth.provider import AuthenticationError

_BEARER_SCHEME = "bearer"


class VerifiedIdentity:
    """A verified caller identity resolved from a bearer token.

    Attributes:
        user_id: The stable platform user id (the token's ``sub`` claim).
        email: The caller's email address if present in the verified claims,
            otherwise ``None``. Safe to surface for display; nothing else from
            the claims is retained.
    """

    __slots__ = ("user_id", "email")

    def __init__(self, user_id: str, email: str | None) -> None:
        """Store the verified user id and optional display email."""
        self.user_id = user_id
        self.email = email


def _unauthorized(detail: str) -> HTTPException:
    """Build a 401 response that leaks neither token nor stack trace."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_bearer(
    authorization: str | None,
    provider: FirebaseAuthProvider,
) -> VerifiedIdentity:
    """Verify an ``Authorization`` header and resolve the caller identity.

    Args:
        authorization: The raw ``Authorization`` header value, or ``None`` when
            absent.
        provider: The auth provider used to verify the token. Injected so tests
            can supply a network-free verifier.

    Returns:
        The :class:`VerifiedIdentity` for the caller.

    Raises:
        HTTPException: 401 when the header is missing, malformed, uses the wrong
            scheme, or the token fails verification. The token is never echoed.
    """
    if not authorization:
        raise _unauthorized("Missing Authorization header.")

    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != _BEARER_SCHEME or not credential.strip():
        raise _unauthorized("Invalid Authorization header; expected 'Bearer <token>'.")

    try:
        provider.set_token(credential.strip())
        user_id = provider.get_user_id()
    except AuthenticationError:
        # Deliberately opaque: do not echo the token or the underlying reason.
        raise _unauthorized("Invalid or expired credentials.") from None

    email = provider.claims.get("email")
    return VerifiedIdentity(user_id=user_id, email=email if isinstance(email, str) else None)
