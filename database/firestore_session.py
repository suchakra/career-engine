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
            Accepts any object with the async Firestore client surface (an
            in-memory test double, or a real ``google.cloud.firestore.AsyncClient``
            in production).  If ``None`` (default), ``get_firestore_client()`` is called.
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
            client: Optional injected Firestore client (real or in-memory test double).
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
