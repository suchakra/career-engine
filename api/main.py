"""FastAPI application for CareerEngine.

Defines the ``app`` and its first two routes: an unauthenticated liveness probe
and a protected identity edge. Auth is enforced at a single dependency
(:func:`api.deps.get_current_identity`), reusing the existing Firebase token
verification (AD-16.4). No business logic lives in this layer.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.auth import VerifiedIdentity
from api.deps import get_current_identity
from api.frontend import mount_frontend
from api.plugins import load_plugins
from api.routes_grill import router as grill_router
from api.routes_read import router as read_router
from api.routes_tailor import router as tailor_router
from api.routes_write import router as write_router

app = FastAPI(title="CareerEngine API")
app.include_router(read_router)
app.include_router(write_router)
app.include_router(grill_router)
app.include_router(tailor_router)

# Open-core seam (ARCHITECTURE §17): mount any installed private plugin routers AFTER
# the core routers. No-op in the OSS/demo build (no plugins installed).
load_plugins(app)


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


@app.api_route(
    "/api/{_rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
def api_not_found(_rest: str) -> JSONResponse:
    """Return a JSON 404 for any unmatched ``/api`` path.

    Registered after every real ``/api`` route but BEFORE the static frontend mount, so
    an unknown API path gets a JSON 404 (not the SPA's HTML ``404.html``) — API clients
    keep getting API-shaped errors.
    """
    return JSONResponse({"detail": "Not Found"}, status_code=404)


# Single-container topology (10.7 / AD-16.10): serve the built Next.js static export at
# '/' — mounted LAST, after EVERY /api route (routers, plugins, health, me, the /api
# JSON-404 catch-all), because a StaticFiles mount at '/' is a catch-all that would
# otherwise shadow later /api routes. No-op when there is no build present (test/dev).
mount_frontend(app)
