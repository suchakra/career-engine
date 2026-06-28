"""Firestore-backed ADK SessionService adapter — typed stub.

Phase 0 — interface and type signatures only.  No real Firestore I/O.
Phase 1 (WS-C) implements the body of each method.

The adapter wraps google.adk.sessions.BaseSessionService so ADK's Runner can
use Firestore as the session persistence backend.

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
    model_dump_json() / model_validate_json() using the key "career_engine_state".
"""

from __future__ import annotations

from typing import Any

from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import GetSessionConfig, ListSessionsResponse

from config import CONTRACT_VERSION
from schema import CareerEngineState


class ContractVersionError(Exception):
    """Raised when a Firestore document has an incompatible CONTRACT_VERSION."""


def _check_version(stored_version: str) -> None:
    """Raise ContractVersionError if the stored major version differs from ours.

    Minor / patch differences are accepted (backward-compatible additions).
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
    """Serialise CareerEngineState to a Firestore-safe dict."""
    return {
        "career_engine_state": state.model_dump(mode="json"),
        "contract_version": CONTRACT_VERSION,
    }


def _dict_to_state(doc: dict[str, Any]) -> CareerEngineState:
    """Deserialise a Firestore document dict back to CareerEngineState."""
    stored_version: str = doc.get("contract_version", "0.0.0")
    _check_version(stored_version)
    return CareerEngineState.model_validate(doc["career_engine_state"])


class FirestoreSessionService(BaseSessionService):
    """ADK SessionService backed by Google Cloud Firestore.

    Phase 0 stub — method signatures are final; bodies raise NotImplementedError.
    """

    def __init__(self, *, collection_prefix: str = "sessions") -> None:
        """Initialise the service.

        Args:
            collection_prefix: Root Firestore collection prefix for session docs.
        """
        self._collection_prefix = collection_prefix
        # Phase 1: self._client = get_firestore_client()

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        """Create a new Firestore-backed session; stub for Phase 0."""
        raise NotImplementedError("FirestoreSessionService.create_session is a Phase 1 task.")

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        """Retrieve an existing session from Firestore; stub for Phase 0."""
        raise NotImplementedError("FirestoreSessionService.get_session is a Phase 1 task.")

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str | None = None,
    ) -> ListSessionsResponse:
        """List sessions for a user; stub for Phase 0."""
        raise NotImplementedError("FirestoreSessionService.list_sessions is a Phase 1 task.")

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Delete a session from Firestore; stub for Phase 0."""
        raise NotImplementedError("FirestoreSessionService.delete_session is a Phase 1 task.")
