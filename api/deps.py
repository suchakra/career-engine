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

from fastapi import Depends, Header, HTTPException
from google.adk.sessions import BaseSessionService
from starlette.concurrency import run_in_threadpool

from api.auth import VerifiedIdentity, verify_bearer
from auth.firebase_auth import FirebaseAuthProvider
from auth.key_vault import SecretManagerKeyVault
from auth.provider import KeyVaultError
from cli.app import DiscoverySession
from config import AccessMode, get_settings
from database.firestore_session import FirestoreSessionService
from database.workspace_store import FirestoreWorkspaceStore
from discovery.store import FirestoreLedgerStore
from integration.model_client import GeminiModelClient
from web.session_loader import web_session_id


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


async def get_discovery_session(
    user_id: str = Depends(get_current_user_id),
    session_service: BaseSessionService = Depends(get_session_service),
) -> DiscoverySession:
    """Build a BYOK :class:`DiscoverySession` over the caller's canonical session.

    The grill runs on the user's OWN Gemini quota (BYOK): the key is fetched from
    Secret Manager and passed to a per-request :class:`GeminiModelClient`. The
    session is addressed by the stable per-user id
    (:func:`web.session_loader.web_session_id`) so the API grill shares the SAME
    durable session as the web grill + portfolio.

    The vault ``fetch_key`` is SYNC, so it runs in a threadpool (this dep is async —
    never block the event loop). If the caller has no BYOK key configured, raise 409
    (never a 500) so the client can prompt for one. Tests override this dep wholesale
    (returning a scripted session), so the vault + model client are never touched.

    Args:
        user_id: The verified caller's stable id (auth boundary).
        session_service: The production Firestore session service (injectable).

    Returns:
        A ready-to-drive :class:`DiscoverySession`.

    Raises:
        HTTPException: 409 if no BYOK API key is configured for the caller.
    """
    vault = SecretManagerKeyVault()
    try:
        api_key = await run_in_threadpool(vault.fetch_key, user_id)
    except KeyVaultError as exc:
        raise HTTPException(status_code=409, detail="BYOK API key not configured") from exc
    if not api_key:
        raise HTTPException(status_code=409, detail="BYOK API key not configured")
    return DiscoverySession(
        user_id=user_id,
        access_mode=AccessMode.BYOK,
        model_client=GeminiModelClient(api_key=api_key),
        session_service=session_service,
        app_name=get_settings().app_name,
        session_id=web_session_id(user_id),
    )
