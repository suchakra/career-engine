"""Firestore-backed ADK SessionService adapter.

Phase 0 — typed stubs only.
Phase 1 (WS-C) — full implementation.

Design rules:
- Documents are keyed by user_id (via the ADK session's user_id field).
  Never keyed by API key or its hash.
- Every persisted document is stamped with CONTRACT_VERSION.
- A document with an unknown MAJOR version raises ContractVersionError.
- No secret (API key, token) is ever written to a Firestore document.

ADK 2.0 session model:
    BaseSessionService requires four async methods:
      create_session(app_name, user_id, state, session_id) -> Session
      get_session(app_name, user_id, session_id, config)   -> Session | None
      list_sessions(app_name, user_id)                     -> ListSessionsResponse
      delete_session(app_name, user_id, session_id)        -> None
    append_event() has a default implementation in the base class.

    The ADK Session object (google.adk.sessions.Session) carries 'state' as a
    plain dict[str, Any].  CareerEngineState is serialised in / out via
    model_dump_json() / model_validate_json() under the key "career_engine_state".

Firestore document layout:
    Document path:
        {collection_prefix}/{app_name}/users/{user_id}/sessions/{session_id}
    Document fields:
        contract_version    : str   (semver, e.g. "1.0.0")
        app_name            : str
        user_id             : str
        session_id          : str
        last_update_time    : float
        career_engine_state : dict  (CareerEngineState.model_dump(mode="json"))
        session_state       : dict  (remaining ADK-internal state keys)

    IMPORTANT: no field ever contains a secret, API key, or token.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import GetSessionConfig, ListSessionsResponse

from config import CONTRACT_VERSION, get_firestore_client
from schema import CareerEngineState

# ── Contract version helpers ──────────────────────────────────────────────────


class ContractVersionError(Exception):
    """Raised when a Firestore document has an incompatible CONTRACT_VERSION."""


def _check_version(stored_version: str) -> None:
    """Raise ContractVersionError if the stored major version differs from ours.

    Minor / patch differences are accepted (backward-compatible additions).

    Args:
        stored_version: The semver string read from the Firestore document.

    Raises:
        ContractVersionError: If the major version component differs.
    """
    stored_major = stored_version.split(".")[0]
    current_major = CONTRACT_VERSION.split(".")[0]
    if stored_major != current_major:
        raise ContractVersionError(
            f"Incompatible contract version in Firestore document: "
            f"stored={stored_version!r}, current={CONTRACT_VERSION!r}. "
            "Migration required before reading this document."
        )


def _state_to_dict(state: CareerEngineState) -> dict[str, Any]:
    """Serialise CareerEngineState to a Firestore-safe dict.

    Args:
        state: The CareerEngineState to serialise.

    Returns:
        A plain dict suitable for embedding in a Firestore document.
    """
    return {
        "career_engine_state": state.model_dump(mode="json"),
        "contract_version": CONTRACT_VERSION,
    }


def _dict_to_state(doc: dict[str, Any]) -> CareerEngineState:
    """Deserialise a Firestore document dict back to CareerEngineState.

    Args:
        doc: The raw dict from a Firestore document.

    Returns:
        A validated CareerEngineState instance.

    Raises:
        ContractVersionError: If the stored major version differs from ours.
        KeyError: If "career_engine_state" is missing from the document.
    """
    stored_version: str = doc.get("contract_version", "0.0.0")
    _check_version(stored_version)
    return CareerEngineState.model_validate(doc["career_engine_state"])


# ── In-memory fake client (for test injection) ────────────────────────────────
#
# The real google.cloud.firestore.AsyncClient supports chained calls like:
#   client.collection("a").document("b").collection("c").document("d").set(data)
#
# To replicate this interface with a flat in-memory dict, every node in the
# chain just accumulates path segments and the terminal methods (set, get,
# delete, list_documents) operate on the complete assembled path.
#
# This fake is intentionally minimal — it only implements the surface used by
# FirestoreSessionService.  It is NOT a general Firestore emulator.


class _FakeDocumentSnapshot:
    """Minimal DocumentSnapshot used by the in-memory fake."""

    def __init__(self, data: dict[str, Any] | None, path: str) -> None:
        """Initialise a fake snapshot.

        Args:
            data: The document data, or None if the document does not exist.
            path: The Firestore document path (informational).
        """
        self._data = data
        self.path = path

    @property
    def exists(self) -> bool:
        """True if the document exists in the fake store."""
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        """Return the document data, or None if the document does not exist."""
        return self._data


class _FakeDocumentReference:
    """Minimal async DocumentReference backed by a shared flat dict store.

    Supports .collection() for sub-collection chaining.
    """

    def __init__(self, store: dict[str, dict[str, Any]], path: str) -> None:
        """Initialise a document reference.

        Args:
            store: Shared mutable dict mapping absolute path -> document data.
            path: The absolute Firestore path for this document.
        """
        self._store = store
        self.path = path

    def collection(self, collection_id: str) -> _FakeCollectionReference:
        """Return a sub-collection reference under this document.

        Args:
            collection_id: The sub-collection name.

        Returns:
            A _FakeCollectionReference whose prefix is ``{self.path}/{collection_id}``.
        """
        return _FakeCollectionReference(
            store=self._store, prefix=f"{self.path}/{collection_id}"
        )

    async def set(self, document_data: dict[str, Any], merge: bool = False) -> None:
        """Write document_data to this document path.

        Args:
            document_data: The data to write.
            merge: If True, merge into the existing document instead of overwriting.
        """
        if merge and self.path in self._store:
            self._store[self.path].update(document_data)
        else:
            self._store[self.path] = dict(document_data)

    async def get(self) -> _FakeDocumentSnapshot:
        """Return a snapshot for this document.

        Returns:
            A snapshot whose .exists reflects whether data was stored at this path.
        """
        raw = self._store.get(self.path)
        data = dict(raw) if raw is not None else None
        return _FakeDocumentSnapshot(data=data, path=self.path)

    async def delete(self) -> None:
        """Delete this document if it exists (no-op if absent)."""
        self._store.pop(self.path, None)


class _FakeCollectionReference:
    """Minimal async CollectionReference backed by a shared flat dict store."""

    def __init__(self, store: dict[str, dict[str, Any]], prefix: str) -> None:
        """Initialise a collection reference.

        Args:
            store: Shared mutable dict mapping absolute path -> document data.
            prefix: The absolute path prefix for this collection (no trailing slash).
        """
        self._store = store
        self._prefix = prefix.rstrip("/")

    def document(self, doc_id: str) -> _FakeDocumentReference:
        """Return a reference to a document in this collection.

        Args:
            doc_id: The document ID.

        Returns:
            A _FakeDocumentReference at ``{prefix}/{doc_id}``.
        """
        return _FakeDocumentReference(store=self._store, path=f"{self._prefix}/{doc_id}")

    async def list_documents(self) -> list[_FakeDocumentReference]:
        """Return references to all existing direct-child documents.

        Only documents that are direct children of this collection (no further
        path segments after the document ID) are returned.

        Returns:
            A list of _FakeDocumentReference objects, one per existing document.
        """
        col_prefix = self._prefix + "/"
        seen: dict[str, bool] = {}
        refs: list[_FakeDocumentReference] = []
        for path in list(self._store.keys()):
            if path.startswith(col_prefix):
                remainder = path[len(col_prefix):]
                doc_id = remainder.split("/")[0]
                doc_path = col_prefix + doc_id
                if doc_id and doc_path not in seen:
                    seen[doc_path] = True
                    refs.append(_FakeDocumentReference(store=self._store, path=doc_path))
        return refs


class FakeFirestoreClient:
    """In-memory Firestore client for unit tests.

    Mimics the async Firestore client interface used by FirestoreSessionService.
    The backing store is a flat dict keyed by the full Firestore document path.

    Example::

        client = FakeFirestoreClient()
        service = FirestoreSessionService(client=client)
    """

    def __init__(self) -> None:
        """Initialise the in-memory store."""
        self._store: dict[str, dict[str, Any]] = {}

    def collection(self, path: str) -> _FakeCollectionReference:
        """Return a top-level collection reference.

        Args:
            path: The collection path (top-level name or slash-separated path).

        Returns:
            A _FakeCollectionReference for the given path.
        """
        return _FakeCollectionReference(store=self._store, prefix=path.strip("/"))

    @property
    def store(self) -> dict[str, dict[str, Any]]:
        """Expose the raw backing store for test assertions (read-only access)."""
        return self._store


# ── FirestoreSessionService ───────────────────────────────────────────────────


class FirestoreSessionService(BaseSessionService):
    """ADK SessionService backed by Google Cloud Firestore.

    Documents are keyed by user_id; no secret is ever persisted.
    Every document is stamped with CONTRACT_VERSION.

    The constructor accepts an optional ``client`` for test injection.  In
    production, leave ``client=None`` and the service will call
    ``get_firestore_client()`` to obtain a real Firestore async client.

    Args:
        collection_prefix: Root Firestore collection name for session docs.
            Defaults to ``"sessions"``.  Full document path per session:
            ``{collection_prefix}/{app_name}/users/{user_id}/sessions/{session_id}``.
        client: Optional Firestore client for dependency injection.
            Accepts a ``FakeFirestoreClient`` for unit tests or a real
            ``google.cloud.firestore.AsyncClient`` in production.
            If ``None`` (default), ``get_firestore_client()`` is called.
    """

    def __init__(
        self,
        *,
        collection_prefix: str = "sessions",
        client: Any | None = None,
    ) -> None:
        """Initialise the service.

        Args:
            collection_prefix: Root Firestore collection prefix for session docs.
            client: Optional injected Firestore client (e.g. FakeFirestoreClient).
        """
        self._collection_prefix = collection_prefix
        self._client: Any = client if client is not None else get_firestore_client()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _session_doc_ref(self, app_name: str, user_id: str, session_id: str) -> Any:
        """Return a Firestore document reference for the given session.

        Document path:
            ``{collection_prefix}/{app_name}/users/{user_id}/sessions/{session_id}``

        Documents are keyed by ``user_id`` (stable auth identity), never by any
        API key or derivative (see ARCHITECTURE.md §5).

        Args:
            app_name: The ADK application name.
            user_id: The authenticated user's stable ID.
            session_id: The ADK session ID.

        Returns:
            A Firestore document reference.
        """
        return (
            self._client
            .collection(self._collection_prefix)
            .document(app_name)
            .collection("users")
            .document(user_id)
            .collection("sessions")
            .document(session_id)
        )

    def _sessions_col_ref(self, app_name: str, user_id: str) -> Any:
        """Return a Firestore collection reference for a user's sessions.

        Args:
            app_name: The ADK application name.
            user_id: The authenticated user's stable ID.

        Returns:
            A Firestore collection reference.
        """
        return (
            self._client
            .collection(self._collection_prefix)
            .document(app_name)
            .collection("users")
            .document(user_id)
            .collection("sessions")
        )

    def _build_session_document(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        session_state: dict[str, Any],
        last_update_time: float,
    ) -> dict[str, Any]:
        """Build a Firestore document dict from session fields.

        Extracts ``CareerEngineState`` from ``session_state["career_engine_state"]``
        if present; remaining ADK-internal state keys (``app:*``, ``user:*``, etc.)
        are stored under the ``session_state`` sub-key.

        SECURITY: The ``CareerEngineState`` schema (schema.py) guarantees it
        carries no secrets.  This method does not add any additional secret-bearing
        fields.

        Args:
            app_name: The ADK application name.
            user_id: The authenticated user's stable ID.
            session_id: The ADK session ID.
            session_state: The ADK session's ``state`` dict.
            last_update_time: POSIX timestamp of the last update.

        Returns:
            A Firestore-safe dict ready for ``.set()``.
        """
        raw_ces = session_state.get("career_engine_state")
        if isinstance(raw_ces, dict):
            career_engine_state_dict: dict[str, Any] = raw_ces
        elif isinstance(raw_ces, str):
            ces = CareerEngineState.model_validate_json(raw_ces)
            career_engine_state_dict = ces.model_dump(mode="json")
        else:
            # No CareerEngineState provided — persist a default empty state
            career_engine_state_dict = CareerEngineState().model_dump(mode="json")

        # Store remaining ADK-internal state keys separately
        other_state: dict[str, Any] = {
            k: v for k, v in session_state.items() if k != "career_engine_state"
        }

        return {
            "contract_version": CONTRACT_VERSION,
            "app_name": app_name,
            "user_id": user_id,
            "session_id": session_id,
            "last_update_time": last_update_time,
            "career_engine_state": career_engine_state_dict,
            "session_state": other_state,
        }

    def _session_from_doc(self, doc_data: dict[str, Any]) -> Session:
        """Reconstruct an ADK Session from a Firestore document dict.

        Args:
            doc_data: The raw Firestore document dict.

        Returns:
            An ADK Session whose ``state`` dict carries ``career_engine_state``
            (as a dict) plus any other ADK-internal state keys.

        Raises:
            ContractVersionError: If the stored major version differs from ours.
            KeyError: If required fields are missing from the document.
        """
        _check_version(doc_data.get("contract_version", "0.0.0"))

        ces_dict: dict[str, Any] = doc_data["career_engine_state"]
        other_state: dict[str, Any] = doc_data.get("session_state", {})
        state: dict[str, Any] = {"career_engine_state": ces_dict, **other_state}

        return Session(
            id=doc_data["session_id"],
            app_name=doc_data["app_name"],
            user_id=doc_data["user_id"],
            state=state,
            last_update_time=doc_data.get("last_update_time", 0.0),
        )

    # ── BaseSessionService methods ────────────────────────────────────────────

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        """Create a new Firestore-backed session.

        The session document is stored at:
            ``{collection_prefix}/{app_name}/users/{user_id}/sessions/{session_id}``

        No API key or secret is ever written to Firestore.

        Args:
            app_name: The ADK application name.
            user_id: The authenticated user's stable ID.
            state: Optional initial state dict.  May contain
                ``"career_engine_state"`` (a CareerEngineState dict or JSON str).
            session_id: Optional caller-supplied session ID.  A UUID4 is
                generated if not provided.

        Returns:
            The newly created ADK Session.
        """
        sid = (session_id or str(uuid.uuid4())).strip()
        now = time.time()

        doc_data = self._build_session_document(
            app_name=app_name,
            user_id=user_id,
            session_id=sid,
            session_state=state or {},
            last_update_time=now,
        )

        doc_ref = self._session_doc_ref(app_name, user_id, sid)
        await doc_ref.set(doc_data)

        return self._session_from_doc(doc_data)

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        """Retrieve an existing session from Firestore.

        Args:
            app_name: The ADK application name.
            user_id: The authenticated user's stable ID.
            session_id: The ADK session ID.
            config: Optional filter config.  The Firestore backend does not
                persist events, so event-related filters are accepted but have
                no effect.

        Returns:
            The ADK Session, or None if no such session exists.

        Raises:
            ContractVersionError: If the stored major version differs from ours.
        """
        doc_ref = self._session_doc_ref(app_name, user_id, session_id)
        snapshot = await doc_ref.get()

        if not snapshot.exists:
            return None

        doc_data = snapshot.to_dict()
        if doc_data is None:
            return None

        return self._session_from_doc(doc_data)

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str | None = None,
    ) -> ListSessionsResponse:
        """List sessions for a user.

        Per the ADK contract, returned Session objects do NOT include events.

        Args:
            app_name: The ADK application name.
            user_id: If provided, list only this user's sessions.  Cross-user
                listing (``user_id=None``) is not supported in this adapter;
                an empty response is returned.

        Returns:
            A ListSessionsResponse containing the matching sessions
            (events field is empty in each Session).
        """
        if user_id is None:
            # Cross-user listing is not implemented in this adapter.
            return ListSessionsResponse()

        col_ref = self._sessions_col_ref(app_name, user_id)
        doc_refs = await col_ref.list_documents()

        sessions: list[Session] = []
        for doc_ref in doc_refs:
            snapshot = await doc_ref.get()
            if not snapshot.exists:
                continue
            doc_data = snapshot.to_dict()
            if doc_data is None:
                continue
            try:
                session = self._session_from_doc(doc_data)
                # ADK contract: list_sessions omits events and full state
                session.events = []
                sessions.append(session)
            except (ContractVersionError, KeyError):
                # Skip incompatible or malformed documents
                continue

        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Delete a session from Firestore.

        No-op if the session does not exist.

        Args:
            app_name: The ADK application name.
            user_id: The authenticated user's stable ID.
            session_id: The ADK session ID to delete.
        """
        doc_ref = self._session_doc_ref(app_name, user_id, session_id)
        await doc_ref.delete()
