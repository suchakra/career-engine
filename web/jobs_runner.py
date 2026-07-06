"""Web discovery runner (Phase 7B) — wires BYOK + the discovery engine into the UI.

The engine (``discovery/``) is reused wholesale: this module only builds a Primary
agent on the user's BYOK key and drives the async loop from Streamlit's sync thread
via the persistent :func:`web.async_runner.run_async` loop (the Scout is async).

Split for testability:
- :func:`build_web_primary` — the BYOK wiring (constructs the Gemini client → Pro-tier
  ``ModelEvaluator`` → ``PrimaryAgent``). Not exercised offline (needs a client).
- :func:`run_web_discovery` — runs a pre-built Primary + persists accepted jobs by
  reusing the tested :func:`discovery.cli.run_discover` (with a no-op output sink) on
  the ``run_async`` loop. Fully testable with a fake Scout + in-memory store.
"""

from __future__ import annotations

import logging

from config import AccessMode
from discovery.primary import DiscoveryResult, ModelEvaluator, PrimaryAgent
from discovery.scout import Scout
from discovery.store import FirestoreLedgerStore, InMemoryLedgerStore, LedgerStore
from schema import InteractionLedger, SessionPreferences
from web.async_runner import run_async

_log = logging.getLogger(__name__)


def resolve_ledger_store(*, use_firestore: bool = True) -> LedgerStore:
    """Return a Firestore-backed ledger store, falling back to in-memory on failure.

    A Firestore construction failure is **logged** (not silent) before the
    in-memory downgrade — otherwise discovery would non-persistently "succeed" with
    no operator signal.
    """
    if use_firestore:
        try:
            return FirestoreLedgerStore()
        except Exception:
            _log.warning(
                "Firestore ledger store unavailable; discovered jobs will NOT persist "
                "(using in-memory store).",
                exc_info=True,
            )
            return InMemoryLedgerStore()
    return InMemoryLedgerStore()


def build_web_primary(
    *,
    api_key: str,
    preferences: SessionPreferences,
    ledger: InteractionLedger,
    scout: Scout | None = None,
    desired_total: int = 5,
    max_iterations: int = 3,
) -> PrimaryAgent:
    """Wire a Primary agent for the web: BYOK Gemini client → Pro-tier evaluator."""
    from integration.model_client import GeminiModelClient

    client = GeminiModelClient(api_key=api_key)
    return PrimaryAgent(
        prefs=preferences,
        ledger=ledger,
        scout=scout or Scout(),
        evaluator=ModelEvaluator(client, access_mode=AccessMode.BYOK),
        desired_total=desired_total,
        max_iterations=max_iterations,
    )


def run_web_discovery(
    *,
    user_id: str,
    primary: PrimaryAgent,
    store: LedgerStore,
) -> DiscoveryResult:
    """Run the bounded discovery loop on the persistent loop and persist accepted jobs.

    Reuses the tested :func:`discovery.cli.run_discover` (prints via a no-op sink,
    records accepted to ``store``, returns the accumulated result).
    """
    from discovery.cli import run_discover

    return run_async(
        run_discover(user_id=user_id, primary=primary, store=store, out=lambda _s: None)
    )


__all__ = ["build_web_primary", "resolve_ledger_store", "run_web_discovery"]
