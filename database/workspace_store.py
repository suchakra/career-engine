"""Firestore-backed UserWorkspace repository (Phase 2).

The concrete :class:`~jobs.pending_action_sweep.WorkspaceStore` used by the
async sweep (2D) and the web dashboard (2A) so web + CLI share per-user
portfolio state (applications + pending actions).

Design:
- Documents are keyed by ``user_id`` (stable auth identity, ARCHITECTURE §5),
  never by an API key. Path: ``{collection_prefix}/{user_id}``.
- Every document is stamped with ``CONTRACT_VERSION``; an unknown MAJOR version
  is refused (reuses the session adapter's version gate). No secret is written.
- The Firestore client surface is async (matching the real
  ``google.cloud.firestore.AsyncClient`` and the in-memory test double), but the
  ``WorkspaceStore`` protocol the sweep uses is SYNC. This class bridges the two
  with ``asyncio.run`` per call — fine for a periodic batch job / request-scoped
  dashboard load, and it keeps the sweep orchestration simple and sync-testable.
"""

from __future__ import annotations

import asyncio
from typing import Any

from config import CONTRACT_VERSION, get_firestore_async_client
from database.firestore_session import ContractVersionError, check_version
from schema import UserWorkspace

_WORKSPACE_KEY = "workspace"


class FirestoreWorkspaceStore:
    """Sync WorkspaceStore backed by an async Firestore client."""

    def __init__(
        self,
        *,
        collection_prefix: str = "workspaces",
        client: Any | None = None,
    ) -> None:
        """Initialise the store.

        Args:
            collection_prefix: Root collection holding one doc per user_id.
            client: Optional injected Firestore client (real async client or an
                in-memory test double). ``None`` → ``get_firestore_client()``.
        """
        self._prefix = collection_prefix
        self._client: Any = client if client is not None else get_firestore_async_client()

    # ── Firestore refs ────────────────────────────────────────────────────────

    def _doc_ref(self, user_id: str) -> Any:
        """Document reference for a user's workspace: ``{prefix}/{user_id}``."""
        return self._client.collection(self._prefix).document(user_id)

    def _col_ref(self) -> Any:
        """Collection reference holding all user workspace docs."""
        return self._client.collection(self._prefix)

    # ── Async internals ───────────────────────────────────────────────────────

    async def _alist_user_ids(self) -> list[str]:
        docs = await self._col_ref().list_documents()
        return [ref.path.rsplit("/", 1)[-1] for ref in docs]

    async def _aload(self, user_id: str) -> UserWorkspace:
        snapshot = await self._doc_ref(user_id).get()
        if not snapshot.exists:
            return UserWorkspace()  # a brand-new user has an empty workspace
        data = snapshot.to_dict() or {}
        check_version(data.get("contract_version", "0.0.0"))
        return UserWorkspace.model_validate(data[_WORKSPACE_KEY])

    async def _asave(self, user_id: str, workspace: UserWorkspace) -> None:
        document = {
            "contract_version": CONTRACT_VERSION,
            "user_id": user_id,  # the doc key, for query/debug convenience
            _WORKSPACE_KEY: workspace.model_dump(mode="json"),
        }
        await self._doc_ref(user_id).set(document)

    # ── Sync WorkspaceStore protocol ──────────────────────────────────────────
    #
    # CONSTRAINT: these use asyncio.run(), which raises if called from a thread
    # that already has a running event loop. Callers must be sync: the sweep job
    # (run_sweep is sync) and the Streamlit script thread (no loop) are both
    # safe. Do NOT call from an async def / coroutine.

    def list_user_ids(self) -> list[str]:
        """Return the user_ids that have a workspace document. (Sync-only — see above.)"""
        return asyncio.run(self._alist_user_ids())

    def load(self, user_id: str) -> UserWorkspace:
        """Load a user's workspace (empty workspace if none persisted yet).

        Raises:
            ContractVersionError: if the stored doc has an incompatible MAJOR version.
        """
        return asyncio.run(self._aload(user_id))

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        """Persist a user's workspace, stamped with CONTRACT_VERSION."""
        asyncio.run(self._asave(user_id, workspace))


class InMemoryWorkspaceStore:
    """Minimal in-memory WorkspaceStore for fallback / testing (no persistence)."""

    def __init__(self) -> None:
        self._store: dict[str, UserWorkspace] = {}

    def list_user_ids(self) -> list[str]:
        return list(self._store)

    def load(self, user_id: str) -> UserWorkspace:
        return self._store.get(user_id, UserWorkspace())

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        self._store[user_id] = workspace


__all__ = ["ContractVersionError", "FirestoreWorkspaceStore", "InMemoryWorkspaceStore"]
