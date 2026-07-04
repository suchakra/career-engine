"""Run coroutines on ONE persistent event loop (Streamlit ⇄ async bridge).

Why this exists: the web layer is synchronous (Streamlit reruns a script top to
bottom), but the ADK session service + async Firestore client are async. The
obvious bridge — ``asyncio.run(coro)`` per call — creates and then **closes** a
fresh event loop every time. That breaks any async client that is REUSED across
calls: the async Firestore client's gRPC channel binds to the loop it was first
used on, so the next ``asyncio.run`` (new loop) fails with
``RuntimeError: Event loop is closed`` the moment that cached client is touched
again (e.g. the grill's cached ``FirestoreSessionService`` across turns).

Fix: keep a single long-lived event loop on a dedicated daemon thread for the
whole process and submit every coroutine to it via
``run_coroutine_threadsafe``. All async work runs on that one loop, so a reused
client's channel stays valid for the life of the server. Submissions are
serialized on the loop thread (thread-safe), which suits the single-instance
web app. ``run_async`` blocks the calling (script) thread until the coroutine
finishes and re-raises any exception, so callers keep their existing try/except.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Return the shared background loop, starting its thread on first use."""
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever, name="ce-async-loop", daemon=True
            )
            thread.start()
            _loop = loop
        return _loop


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion on the shared loop and return its result.

    Blocks the caller until done; re-raises any exception from the coroutine.
    """
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


__all__ = ["run_async"]
