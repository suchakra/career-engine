"""FastAPI application for CareerEngine.

Defines the ``app`` and its first two routes: an unauthenticated liveness probe
and a protected identity edge. Auth is enforced at a single dependency
(:func:`api.deps.get_current_identity`), reusing the existing Firebase token
verification (AD-16.4). No business logic lives in this layer.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from api.auth import VerifiedIdentity
from api.deps import get_current_identity

app = FastAPI(title="CareerEngine API")


class HealthResponse(BaseModel):
    """Liveness response body."""

    status: str


class MeResponse(BaseModel):
    """Verified identity response body (safe display info only)."""

    user_id: str
    email: str | None = None


@app.get("/api/health")
def health() -> HealthResponse:
    """Return a liveness signal. Unauthenticated.

    Returns:
        A :class:`HealthResponse` with ``status == "ok"``.
    """
    return HealthResponse(status="ok")


@app.get("/api/me")
def me(identity: VerifiedIdentity = Depends(get_current_identity)) -> MeResponse:
    """Return the verified caller's identity. Requires a valid bearer token.

    Args:
        identity: The verified caller identity resolved at the auth boundary.

    Returns:
        A :class:`MeResponse` with the stable ``user_id`` and, when present, the
        caller's email. The raw token is never returned.
    """
    return MeResponse(user_id=identity.user_id, email=identity.email)
