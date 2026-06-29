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


async def patch_state(
    *,
    session_service: BaseSessionService,
    app_name: str,
    user_id: str,
    session_id: str,
    **fields: Any,
) -> None:
    """Apply field-level patches to the CareerEngineState of an ADK session.

    Reads the current session, updates the specified fields in the backing
    flat dict, and writes the result back.  Used by the CLI loop to inject
    ``pending_user_answer`` and ``checkpoint_verified`` between Runner turns.

    Note: ``InMemorySessionService`` holds sessions in a dict that the Runner
    also references; patching the dict's values is visible to the next
    ``runner.run_async`` call.

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
    for key, value in fields.items():
        session.state[key] = value


def run_sync(coro: Any) -> Any:
    """Run a coroutine synchronously (CLI helper for non-async contexts).

    Wraps ``asyncio.run`` so callers don't need to import asyncio.

    Args:
        coro: An awaitable coroutine.

    Returns:
        The result of the coroutine.
    """
    return asyncio.run(coro)
