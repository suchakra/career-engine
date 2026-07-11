"""Protected job-discovery RUN route (parity P2).

``GET /api/jobs`` (10.2) only reads previously-accepted matches. This runs the bounded
two-agent discovery loop (Scout ⇄ MCP ⇄ Primary) on the caller's BYOK key + saved rubric,
persists accepted matches to the ledger, and returns the FRESH ``JobsView``. Reuses
``web.jobs_runner`` (the tested run) — no new discovery logic here. The run is sync +
blocking (own persistent loop), so it executes in a threadpool.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from api.deps import (
    get_current_user_id,
    get_key_vault,
    get_ledger_store,
    get_workspace_store,
)
from api.schemas import JobsResponse
from auth.key_vault import SecretManagerKeyVault
from auth.provider import KeyVaultError
from database.workspace_store import FirestoreWorkspaceStore
from discovery.store import FirestoreLedgerStore
from web.jobs import build_jobs_view
from web.jobs_runner import build_web_primary, run_web_discovery
from web.preferences_store import load_discovery_preferences

router = APIRouter()


@router.post("/api/jobs/discover")
async def discover_jobs(
    user_id: str = Depends(get_current_user_id),
    vault: SecretManagerKeyVault = Depends(get_key_vault),
    ledger_store: FirestoreLedgerStore = Depends(get_ledger_store),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> JobsResponse:
    """Run job discovery on the caller's BYOK key + saved rubric; return fresh matches.

    409 if no BYOK key is configured (the run consumes the user's own Gemini quota).
    """
    try:
        api_key = await run_in_threadpool(vault.fetch_key, user_id)
    except KeyVaultError as exc:
        raise HTTPException(status_code=409, detail="BYOK API key not configured") from exc
    if not api_key:
        raise HTTPException(status_code=409, detail="BYOK API key not configured")

    def _run() -> JobsResponse:
        preferences = load_discovery_preferences(workspace_store, user_id=user_id)
        ledger = ledger_store.load_ledger(user_id)
        primary = build_web_primary(
            api_key=api_key, preferences=preferences, ledger=ledger
        )
        result = run_web_discovery(
            user_id=user_id, primary=primary, store=ledger_store
        )
        hidden = set(ledger.rejected_companies)
        return JobsResponse.from_view(build_jobs_view(result, hidden_companies=hidden))

    return await run_in_threadpool(_run)
