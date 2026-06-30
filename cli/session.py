"""Session-state helpers for the CLI multi-turn loop.

Provides thin helpers that bridge the ADK InMemorySessionService (or
FirestoreSessionService) and the CareerEngineState Pydantic model.

Design rules:
- State is always read from / written to the ADK session service.
- Never cache state in a module-level variable (no shared mutable globals).
- All helpers are async to match the ADK session service interface.
- No UI code (no print / input calls).
"""

from __future__ import annotations

import asyncio
from typing import Any

from google.adk.events import Event, EventActions
from google.adk.sessions import BaseSessionService, Session

from schema import CareerEngineState


async def create_session(
    *,
    session_service: BaseSessionService,
    app_name: str,
    user_id: str,
    session_id: str,
    initial_state: CareerEngineState,
) -> Session:
    """Create a new ADK session seeded with the given CareerEngineState.

    Serialises the Pydantic model to a flat dict so that the ADK shims
    (which read field-by-field from ctx.state) find the correct keys.

    Args:
        session_service: The ADK session service to use.
        app_name: ADK application name (must match the Runner's app_name).
        user_id: The authenticated user's stable platform ID.
        session_id: Caller-supplied session ID (unique per session).
        initial_state: The starting CareerEngineState for this session.

    Returns:
        The newly created ADK Session.
    """
    flat: dict[str, Any] = initial_state.model_dump(mode="json")
    return await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=flat,
    )


async def read_state(
    *,
    session_service: BaseSessionService,
    app_name: str,
    user_id: str,
    session_id: str,
) -> CareerEngineState:
    """Read the current CareerEngineState from an ADK session.

    Args:
        session_service: The ADK session service.
        app_name: ADK application name.
        user_id: The authenticated user's stable platform ID.
        session_id: The session to read.

    Returns:
        The current CareerEngineState, validated from the session's flat state dict.

    Raises:
        ValueError: if the session does not exist.
    """
    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise ValueError(
            f"Session {session_id!r} not found for user {user_id!r} / app {app_name!r}."
        )
    return CareerEngineState.model_validate(session.state)


async def get_session_state_if_exists(
    *,
    session_service: BaseSessionService,
    app_name: str,
    user_id: str,
    session_id: str,
) -> CareerEngineState | None:
    """Return the persisted CareerEngineState for a session, or None if absent.

    The load-before-create primitive behind true session resume (Phase 1.7-B):
    callers use this to reuse an existing session instead of blindly calling
    ``create_session`` (which is last-write-wins and would clobber prior
    progress).  Unlike :func:`read_state`, a missing session is NOT an error —
    it returns ``None`` so a brand-new session can start cleanly.

    Args:
        session_service: The ADK session service.
        app_name: ADK application name.
        user_id: The authenticated user's stable platform ID.
        session_id: The session to look up.

    Returns:
        The validated CareerEngineState if the session exists, else ``None``.
    """
    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        return None
    return CareerEngineState.model_validate(session.state)


async def read_raw_state(
    *,
    session_service: BaseSessionService,
    app_name: str,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Read the raw flat session-state dict, including non-contract keys.

    Unlike :func:`read_state` — which validates into ``CareerEngineState`` and
    therefore drops any key that is not a contract field — this returns the
    unfiltered state dict.  The CLI uses it to inspect side-channel signals the
    workflow shims write outside the schema, notably ``_upgrade_required``
    (a serialized :class:`~schema.UpgradeRequired`).  This is the v1.1.x
    band-aid for REVIEW.md #1; the v2.0.0 contract promotes it to a typed field.

    Args:
        session_service: The ADK session service.
        app_name: ADK application name.
        user_id: The authenticated user's stable platform ID.
        session_id: The session to read.

    Returns:
        A shallow copy of the session's flat state dict.

    Raises:
        ValueError: if the session does not exist.
    """
    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise ValueError(
            f"Session {session_id!r} not found for user {user_id!r} / app {app_name!r}."
        )
    return dict(session.state)


async def patch_state(
    *,
    session_service: BaseSessionService,
    app_name: str,
    user_id: str,
    session_id: str,
    **fields: Any,
) -> None:
    """Apply field-level patches to the CareerEngineState of an ADK session.

    Injects the patched fields into the session by appending an Event carrying
    an ``EventActions(state_delta=...)``.  Used by the CLI loop to inject
    ``pending_user_answer`` and ``checkpoint_verified`` between Runner turns.

    Why an event (and not a direct dict write): ADK session services return a
    COPY of the session from ``get_session``, so mutating that copy's ``state``
    is not persisted and is invisible to the next ``runner.run_async`` call.
    The canonical ADK mechanism for committing external state is to append an
    event whose ``actions.state_delta`` the service merges into the stored
    session — exactly how the workflow's own node writes are persisted.

    Args:
        session_service: The ADK session service.
        app_name: ADK application name.
        user_id: The authenticated user's stable platform ID.
        session_id: The session to patch.
        **fields: CareerEngineState field names mapped to new values.

    Raises:
        ValueError: if the session does not exist.
    """
    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise ValueError(
            f"Session {session_id!r} not found for user {user_id!r} / app {app_name!r}."
        )
    event = Event(
        author="user",
        actions=EventActions(state_delta=dict(fields)),
    )
    await session_service.append_event(session, event)


def run_sync(coro: Any) -> Any:
    """Run a coroutine synchronously (CLI helper for non-async contexts).

    Wraps ``asyncio.run`` so callers don't need to import asyncio.

    Args:
        coro: An awaitable coroutine.

    Returns:
        The result of the coroutine.
    """
    return asyncio.run(coro)
