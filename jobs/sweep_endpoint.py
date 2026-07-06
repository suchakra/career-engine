"""HTTP entrypoint for the 14-day pending-action sweep.

**Primary execution path (WS 8C+): Cloud Scheduler → Cloud Run Job → `career-engine sweep`.**
See ``jobs/sweep_cli.py`` and ``infrastructure/modules/cloud_run_job/``.

This module is retained as an **alternative trigger** (HTTP path). Cloud Scheduler
POSTs to a Cloud Run endpoint with an **OIDC token** whose audience is the service
base URL (see ``infrastructure/modules/scheduler``). This module is the
framework-agnostic core that a thin adapter (Flask / FastAPI / functions-framework)
mounts:

    resp = handle_sweep_request(
        authorization=request.headers.get("Authorization"),
        store=FirestoreWorkspaceStore(),
        today=date.today().isoformat(),
        expected_audiences={service_base_url},
    )
    return resp.body, resp.status

Security (mirrors the FirebaseAuth aud/iss fix): the caller-supplied OIDC token
is verified for a genuine Google signature, and its ``aud`` is pinned to this
service's URL. Unlike the interactive auth path, this privileged endpoint is
**secure-by-default**: if no expected audience is configured, the request is
rejected rather than allowed. There is no ``allUsers`` invoker binding — only the
scheduler's service account can mint an accepted token.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from auth.firebase_auth import google_tokeninfo_verifier
from jobs.pending_action_sweep import DEFAULT_THRESHOLD_DAYS, WorkspaceStore, run_sweep

# Issuers Google mints Cloud Scheduler OIDC tokens under (defense-in-depth,
# consistent with FirebaseAuthProvider — the aud pin is the load-bearing guard).
_ALLOWED_ISSUERS: frozenset[str] = frozenset(
    {"https://accounts.google.com", "accounts.google.com"}
)


@dataclass(frozen=True)
class SweepHttpResponse:
    """A framework-agnostic HTTP response (status + JSON-serializable body)."""

    status: int
    body: dict[str, Any]


def _extract_bearer(authorization: str | None) -> str | None:
    """Return the bearer token from an Authorization header, or None if malformed."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def handle_sweep_request(
    *,
    authorization: str | None,
    store: WorkspaceStore,
    today: str,
    expected_audiences: Iterable[str],
    verifier: Callable[[str], dict[str, Any]] | None = None,
    allowed_service_accounts: Iterable[str] | None = None,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
    log: Callable[[str], None] = print,
) -> SweepHttpResponse:
    """Authenticate an OIDC-signed request, then run the sweep.

    Args:
        authorization: The raw ``Authorization`` header (``Bearer <oidc-token>``).
        store: The workspace persistence surface swept over.
        today: Injected current date (ISO ``YYYY-MM-DD``).
        expected_audiences: Accepted ``aud`` values (the service base URL). Empty
            → every request is rejected (secure-by-default).
        verifier: Token verifier ``(token) -> claims``; defaults to Google's
            tokeninfo endpoint. Injectable for tests.
        allowed_service_accounts: Optional allowlist of token ``email`` claims
            (the scheduler invoker SA); when given, a non-matching email is 403.
        threshold_days: Staleness threshold forwarded to the sweep.
        log: User-safe log sink forwarded to :func:`run_sweep`.

    Returns:
        A :class:`SweepHttpResponse` — 401 (missing/invalid token), 403
        (audience/SA not accepted), or 200 with the sweep report.
    """
    token = _extract_bearer(authorization)
    if token is None:
        return SweepHttpResponse(401, {"error": "missing or malformed Authorization bearer token"})

    verify = verifier if verifier is not None else google_tokeninfo_verifier
    try:
        claims = verify(token)
    except Exception:
        return SweepHttpResponse(401, {"error": "token verification failed"})

    audiences = frozenset(expected_audiences)
    if not audiences or claims.get("aud", "") not in audiences:
        return SweepHttpResponse(403, {"error": "token audience not accepted"})

    if claims.get("iss", "") not in _ALLOWED_ISSUERS:
        return SweepHttpResponse(403, {"error": "token issuer not accepted"})

    if allowed_service_accounts is not None:
        if claims.get("email", "") not in frozenset(allowed_service_accounts):
            return SweepHttpResponse(403, {"error": "token service account not accepted"})

    report = run_sweep(store=store, today=today, threshold_days=threshold_days, log=log)
    return SweepHttpResponse(
        200,
        {
            "users_processed": report.users_processed,
            "users_failed": report.users_failed,
            "pending_actions_created": report.pending_actions_created,
        },
    )
