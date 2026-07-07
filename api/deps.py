"""FastAPI dependency wiring for the transport layer.

Exposes the injectable seams the routes depend on:

- :func:`get_auth_provider` — a factory returning a production
  :class:`~auth.firebase_auth.FirebaseAuthProvider` (real network verifier).
  Tests override this via ``app.dependency_overrides`` to inject a fake,
  network-free verifier.
- :func:`get_current_user_id` — resolves the verified ``user_id`` from the
  request's bearer token, or raises 401.
- :func:`get_current_identity` — the fuller :class:`VerifiedIdentity` for
  handlers that also need safe display info (e.g. email).
"""

from __future__ import annotations

from fastapi import Depends, Header

from api.auth import VerifiedIdentity, verify_bearer
from auth.firebase_auth import FirebaseAuthProvider


def get_auth_provider() -> FirebaseAuthProvider:
    """Return the production auth provider (real Google token verifier).

    This is the seam tests override with ``app.dependency_overrides`` to inject
    a :class:`FirebaseAuthProvider` built with a fake verifier, so no test ever
    touches the network.
    """
    return FirebaseAuthProvider()


def get_current_identity(
    authorization: str | None = Header(default=None),
    provider: FirebaseAuthProvider = Depends(get_auth_provider),
) -> VerifiedIdentity:
    """Resolve the verified caller identity from the ``Authorization`` header.

    Args:
        authorization: The raw ``Authorization`` header (FastAPI-injected).
        provider: The auth provider (injectable for network-free tests).

    Returns:
        The verified :class:`VerifiedIdentity`.

    Raises:
        HTTPException: 401 if the token is missing, malformed, or invalid.
    """
    return verify_bearer(authorization, provider)


def get_current_user_id(
    identity: VerifiedIdentity = Depends(get_current_identity),
) -> str:
    """Return the stable ``user_id`` for the verified caller.

    Args:
        identity: The resolved caller identity.

    Returns:
        The stable ``user_id`` string.
    """
    return identity.user_id
