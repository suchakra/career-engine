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
- :func:`get_session_service` / :func:`get_workspace_store` /
  :func:`get_ledger_store` — read-path store/service factories the read routes
  depend on. Each returns a production instance and is overridden with an
  in-memory fake in tests, so no read endpoint ever touches the network.
"""

from __future__ import annotations

from fastapi import Depends, Header

from api.auth import VerifiedIdentity, verify_bearer
from auth.firebase_auth import FirebaseAuthProvider
from database.firestore_session import FirestoreSessionService
from database.workspace_store import FirestoreWorkspaceStore
from discovery.store import FirestoreLedgerStore


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


def get_session_service() -> FirestoreSessionService:
    """Return the production discovery session service (async Firestore client).

    Constructed per request so the injectable seam stays request-scoped and the
    async client's gRPC channel isn't reused across event loops. Tests override
    this via ``app.dependency_overrides`` to inject an in-memory fake.
    """
    return FirestoreSessionService()


def get_workspace_store() -> FirestoreWorkspaceStore:
    """Return the production workspace store (per-user portfolio doc).

    Tests override this via ``app.dependency_overrides`` to inject an in-memory
    fake exposing ``.load(user_id)``.
    """
    return FirestoreWorkspaceStore()


def get_ledger_store() -> FirestoreLedgerStore:
    """Return the production discovery ledger store (accepted jobs + dismissals).

    Tests override this via ``app.dependency_overrides`` to inject an in-memory
    fake exposing ``.list_accepted(user_id)`` and ``.load_ledger(user_id)``.
    """
    return FirestoreLedgerStore()
