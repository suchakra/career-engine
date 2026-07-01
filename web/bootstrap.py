"""Web auth + session bootstrap (Phase 2B).

Ties the already-built :class:`~auth.firebase_auth.FirebaseAuthProvider`
(Identity Platform token → stable ``user_id``) to the per-user workspace load,
giving the web layer an authenticated, namespaced entry point.

Rules (ARCHITECTURE §5):
- The stable ``user_id`` (the token's ``sub``) is the namespace key for both the
  workspace doc and the discovery session — never an API key.
- BYOK keys stay in Secret Manager via KeyVault; they are NEVER placed on the
  workspace/session payload here.
- Unauthenticated access is rejected via a typed, safe path (no stack leak,
  no partial state).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from auth.provider import AuthenticationError
from schema import UserWorkspace

_log = logging.getLogger(__name__)


class _AuthProviderLike(Protocol):
    """The minimal auth surface bootstrap needs (FirebaseAuthProvider satisfies it)."""

    def set_token(self, id_token: str) -> None: ...
    def get_user_id(self) -> str: ...


class _WorkspaceStoreLike(Protocol):
    """The minimal workspace-load surface bootstrap needs."""

    def load(self, user_id: str) -> UserWorkspace: ...


@dataclass(frozen=True)
class WebSession:
    """An authenticated web session: the namespaced identity + loaded workspace.

    Carries NO secret material — only the stable user_id and the user's
    portfolio workspace.
    """

    user_id: str
    workspace: UserWorkspace


def bootstrap_web_session(
    *,
    id_token: str,
    auth_provider: _AuthProviderLike,
    workspace_store: _WorkspaceStoreLike,
) -> WebSession:
    """Verify a token, resolve the user_id, and load that user's workspace.

    Args:
        id_token: The Identity Platform / Firebase ID token from the frontend.
        auth_provider: Provider that verifies the token and yields a stable user_id.
        workspace_store: Store used to load the user's workspace by user_id.

    Returns:
        A :class:`WebSession` for the authenticated user.

    Raises:
        AuthenticationError: if the token is missing/invalid.
    """
    if not id_token:
        raise AuthenticationError("No ID token provided.")
    auth_provider.set_token(id_token)  # raises AuthenticationError on a bad token
    user_id = auth_provider.get_user_id()
    workspace = workspace_store.load(user_id)
    return WebSession(user_id=user_id, workspace=workspace)


def try_bootstrap_web_session(
    *,
    id_token: str | None,
    auth_provider: _AuthProviderLike,
    workspace_store: _WorkspaceStoreLike,
) -> WebSession | None:
    """Non-raising bootstrap for the UX layer.

    Returns ``None`` when there is no token or verification fails, so the caller
    can render a safe "please sign in" surface instead of crashing.

    Args:
        id_token: The ID token, or ``None`` when the user is not signed in.
        auth_provider: The auth provider.
        workspace_store: The workspace store.

    Returns:
        A :class:`WebSession` when authenticated, else ``None``.
    """
    if not id_token:
        return None
    try:
        return bootstrap_web_session(
            id_token=id_token,
            auth_provider=auth_provider,
            workspace_store=workspace_store,
        )
    except AuthenticationError:
        return None
    except Exception:
        # Any non-auth failure (e.g. ContractVersionError from a workspace load
        # after a contract bump) must NOT crash the UI or leak a stack trace —
        # the caller renders a safe sign-in/empty surface. Log generically (no
        # exception text) so ops can distinguish a schema issue from a bad token.
        _log.warning("web session bootstrap failed for a non-auth reason; rendering sign-in")
        return None
