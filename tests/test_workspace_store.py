"""Tests for the Firestore UserWorkspace repository (Phase 2).

Uses the in-memory async FakeFirestoreClient. Tests are SYNC (the store bridges
to async internally via asyncio.run, which must not run inside another loop).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from config import CONTRACT_VERSION
from database.workspace_store import ContractVersionError, FirestoreWorkspaceStore
from schema import Application, PendingAction, UserWorkspace
from tests.fakes import FakeFirestoreClient


def _store() -> tuple[FirestoreWorkspaceStore, FakeFirestoreClient]:
    client = FakeFirestoreClient()
    return FirestoreWorkspaceStore(client=client), client


def _workspace() -> UserWorkspace:
    return UserWorkspace(
        applications=[Application(company="Acme", applied_on="2026-06-01")],
        pending_actions=[PendingAction(application_id="a1", created_on="2026-06-30")],
    )


class TestWorkspaceStore:
    """FirestoreWorkspaceStore round-trips workspaces keyed by user_id."""

    def test_save_then_load_roundtrip(self) -> None:
        """A saved workspace loads back equal."""
        store, _ = _store()
        ws = _workspace()
        store.save("user-1", ws)
        loaded = store.load("user-1")
        assert loaded == ws

    def test_load_missing_returns_empty_workspace(self) -> None:
        """A user with no persisted doc loads an empty workspace (not an error)."""
        store, _ = _store()
        loaded = store.load("nobody")
        assert loaded == UserWorkspace()
        assert loaded.applications == []

    def test_list_user_ids(self) -> None:
        """list_user_ids returns exactly the users that have workspace docs."""
        store, _ = _store()
        store.save("u1", _workspace())
        store.save("u2", UserWorkspace())
        assert set(store.list_user_ids()) == {"u1", "u2"}

    def test_document_is_keyed_by_user_id(self) -> None:
        """The workspace doc path is {prefix}/{user_id} (never an API key)."""
        store, client = _store()
        store.save("user-xyz", _workspace())
        assert any(path.endswith("workspaces/user-xyz") for path in client.store)

    def test_document_is_contract_stamped(self) -> None:
        """Persisted docs carry the current CONTRACT_VERSION."""
        store, client = _store()
        store.save("u1", _workspace())
        doc = next(v for k, v in client.store.items() if k.endswith("workspaces/u1"))
        assert doc["contract_version"] == CONTRACT_VERSION

    def test_no_secret_fields_persisted(self) -> None:
        """No secret-like keys are written to the workspace document."""
        store, client = _store()
        store.save("u1", _workspace())
        doc = next(v for k, v in client.store.items() if k.endswith("workspaces/u1"))
        forbidden = {"api_key", "token", "password", "secret", "credential"}
        assert forbidden.isdisjoint(doc.keys())

    def test_unknown_major_version_refused(self) -> None:
        """A doc stamped with an incompatible MAJOR version is refused on load."""
        store, client = _store()

        async def _seed() -> None:
            await client.collection("workspaces").document("u1").set(
                {
                    "contract_version": "99.0.0",
                    "user_id": "u1",
                    "workspace": UserWorkspace().model_dump(mode="json"),
                }
            )

        asyncio.run(_seed())
        with pytest.raises(ContractVersionError):
            store.load("u1")

    def test_injected_client_not_closed_by_store(self) -> None:
        """An injected client is used as-is and never closed by the store."""
        client = FakeFirestoreClient()
        store = FirestoreWorkspaceStore(client=client)
        ws = _workspace()
        store.save("u1", ws)
        loaded = store.load("u1")
        assert loaded == ws
        # The injected client was used but never closed.
        assert not client.close_called

    def test_workspace_store_closes_created_client(self) -> None:
        """A store-created client is closed after each async operation."""
        call_count = 0
        clients_created: list[FakeFirestoreClient] = []

        def factory() -> FakeFirestoreClient:
            nonlocal call_count
            call_count += 1
            client = FakeFirestoreClient()
            clients_created.append(client)
            return client

        store = FirestoreWorkspaceStore(client_factory=factory)
        store.save("u1", _workspace())
        store.load("u1")

        # Factory was called once per async operation (save + load = 2).
        assert call_count == 2
        # Each created client was closed.
        assert all(c.close_called for c in clients_created)

    def test_workspace_store_load_then_save_uses_fresh_client_each_call(self) -> None:
        """Load THEN save on ONE store uses a fresh client per call (regression guard for BUG-1)."""
        call_count = 0
        # Shared backing store across all created clients (they need to see each other's writes).
        shared_store: dict[str, dict[str, Any]] = {}

        def factory() -> FakeFirestoreClient:
            nonlocal call_count
            call_count += 1
            client = FakeFirestoreClient()
            # Override the client's internal store with the shared one.
            client._store = shared_store
            return client

        store = FirestoreWorkspaceStore(client_factory=factory)
        ws = _workspace()
        store.save("u1", ws)  # seed a document so the load() below returns real data
        # BUG-1 repro order: save_profile()/save_tailored_application() do load()
        # THEN save() on ONE store. Reusing a single client bound its gRPC channel
        # to the first (now-closed) asyncio.run loop → "Event loop is closed".
        loaded = store.load("u1")  # load()  → asyncio.run
        store.save("u1", loaded)  # save()  → another asyncio.run (previously reused a dead loop)
        assert store.load("u1") == ws
        # The store did NOT reuse a single client: one per async op (save + load + save + load).
        assert call_count == 4
