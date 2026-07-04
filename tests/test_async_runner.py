"""Tests for the shared persistent-loop async bridge (web/async_runner.py).

The bug this fixes: ``asyncio.run`` per call closes its loop, so an async client
reused across calls (the cached Firestore session service) hits
"Event loop is closed". ``run_async`` runs everything on ONE long-lived loop.
"""

from __future__ import annotations

import asyncio

import pytest

from web.async_runner import run_async


async def _echo(value: int) -> int:
    await asyncio.sleep(0)
    return value


async def _boom() -> None:
    raise ValueError("kaboom")


async def _running_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_returns_coroutine_result() -> None:
    assert run_async(_echo(41)) == 41


def test_propagates_exceptions() -> None:
    with pytest.raises(ValueError, match="kaboom"):
        run_async(_boom())


def test_reuses_one_open_loop_across_calls() -> None:
    """The regression guard: successive calls share ONE loop that stays open.

    With ``asyncio.run`` each call would create and CLOSE a distinct loop (the
    condition that breaks a reused gRPC client). ``run_async`` must not.
    """
    loop1 = run_async(_running_loop())
    loop2 = run_async(_running_loop())
    assert loop1 is loop2
    assert not loop1.is_closed()
