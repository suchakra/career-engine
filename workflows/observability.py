"""Observability for the discovery graph (Phase 3 — monitoring/logging).

The turn-based graph can appear to *hang* in two ways: a model call that blocks
on the network, or a turn that runs far longer than expected. This module gives
operators visibility into both without changing any node's pure logic:

- :func:`configure_logging` — idempotent structured logging setup for the
  ``career_engine`` logger tree (level from ``CE_LOG_LEVEL``, default INFO).
- :func:`log_operation` — a context manager that times an operation, logs it at
  start/finish with structured fields, escalates to WARNING when it exceeds a
  ``slow_ms`` budget (the "this looks stuck" signal), and logs + re-raises on
  error. Timing uses a monotonic clock — it never touches ``datetime.now`` and
  never influences graph state (determinism is preserved).

The companion defence against a truly-blocked model call is a request timeout on
the real client (see ``workflows.nodes._default_client_factory``); this module is
the *visibility* half.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

_ROOT_LOGGER_NAME = "career_engine"
_DEFAULT_SLOW_MS = 15_000  # a single operation over 15s is flagged as slow

_configured = False


def configure_logging(*, level: int | str | None = None) -> None:
    """Attach a structured handler to the ``career_engine`` logger (idempotent).

    Safe to call from every entrypoint (CLI, web, jobs); subsequent calls are
    no-ops so we never double-log. The level defaults to ``CE_LOG_LEVEL`` (env)
    then INFO.

    Args:
        level: Explicit level (name or int). When ``None``, ``CE_LOG_LEVEL`` is
            consulted, falling back to INFO.
    """
    global _configured
    if _configured:
        return
    logger = logging.getLogger(_ROOT_LOGGER_NAME)

    resolved = level if level is not None else os.environ.get("CE_LOG_LEVEL", "INFO")
    logger.setLevel(resolved)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False  # own handler; don't double-emit via the root logger
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child of the ``career_engine`` logger."""
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


def _format_fields(fields: Mapping[str, object]) -> str:
    """Render structured fields as sorted ``key=value`` pairs."""
    return " ".join(f"{k}={fields[k]!r}" for k in sorted(fields))


@contextmanager
def log_operation(
    operation: str,
    *,
    logger: logging.Logger,
    slow_ms: float = _DEFAULT_SLOW_MS,
    **fields: object,
) -> Iterator[None]:
    """Time an operation and log its lifecycle with structured fields.

    Emits a DEBUG "start" record, then on exit an INFO "ok" record with
    ``elapsed_ms`` — escalated to WARNING when ``elapsed_ms`` exceeds ``slow_ms``
    (the signal an operator uses to spot a stuck/slow turn or model call). On an
    exception it logs an ERROR record with the elapsed time and re-raises, so the
    failure is visible and never swallowed.

    Args:
        operation: Stable operation name (e.g. ``"model.generate"``).
        logger: The logger to emit on (use :func:`get_logger`).
        slow_ms: Elapsed-time budget in milliseconds; over this → WARNING.
        **fields: Structured context (e.g. ``model_id=..., phase=...``).
    """
    base = _format_fields(fields)
    logger.debug("%s start %s", operation, base)
    start = time.monotonic()
    try:
        yield
    except BaseException as exc:  # log-and-reraise: we surface, never swallow
        elapsed_ms = (time.monotonic() - start) * 1000.0
        logger.error(
            "%s error elapsed_ms=%.1f error=%r %s", operation, elapsed_ms, exc, base
        )
        raise
    elapsed_ms = (time.monotonic() - start) * 1000.0
    if elapsed_ms > slow_ms:
        logger.warning(
            "%s slow elapsed_ms=%.1f slow_ms=%.1f %s", operation, elapsed_ms, slow_ms, base
        )
    else:
        logger.info("%s ok elapsed_ms=%.1f %s", operation, elapsed_ms, base)
