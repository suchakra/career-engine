"""Protected BYOK key-management routes (parity P1).

The web app is BYOK: each user brings their own Gemini key. These endpoints let the
UI set / check / remove that key, stored in Secret Manager (``ce-key-{user_id}``) via
``auth.key_vault``. The raw key is NEVER logged or returned. Sync vault calls run in a
threadpool (these deps are async — never block the event loop).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from api.deps import get_current_user_id, get_key_vault
from api.schemas import KeyStatusResponse, KeyWriteRequest
from auth.key_vault import SecretManagerKeyVault
from auth.provider import KeyVaultError

router = APIRouter()


@router.get("/api/key")
async def key_status(
    user_id: str = Depends(get_current_user_id),
    vault: SecretManagerKeyVault = Depends(get_key_vault),
) -> KeyStatusResponse:
    """Return whether the caller has a saved BYOK key (never the key itself).

    Uses ``key_exists`` so the secret PAYLOAD is never pulled into memory. A genuine
    vault fault surfaces as 502 (not a misleading ``has_key: false``).
    """
    try:
        exists = await run_in_threadpool(vault.key_exists, user_id)
    except KeyVaultError as exc:
        raise HTTPException(status_code=502, detail="Could not check key status.") from exc
    return KeyStatusResponse(has_key=exists)


@router.post("/api/key", status_code=204)
async def set_key(
    body: KeyWriteRequest,
    user_id: str = Depends(get_current_user_id),
    vault: SecretManagerKeyVault = Depends(get_key_vault),
) -> Response:
    """Store the caller's Gemini key in Secret Manager. Returns 204 (no body)."""
    try:
        await run_in_threadpool(vault.store_key, user_id, body.api_key)
    except KeyVaultError as exc:
        raise HTTPException(status_code=502, detail="Could not store the key.") from exc
    return Response(status_code=204)


@router.delete("/api/key", status_code=204)
async def remove_key(
    user_id: str = Depends(get_current_user_id),
    vault: SecretManagerKeyVault = Depends(get_key_vault),
) -> Response:
    """Remove the caller's saved key (idempotent). Returns 204."""
    try:
        await run_in_threadpool(vault.delete_key, user_id)
    except KeyVaultError:
        pass  # already absent — delete is idempotent
    return Response(status_code=204)
