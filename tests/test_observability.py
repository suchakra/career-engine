"""Tests for workflows/observability.py + the monitored model-client wrapper.

No live logging config is left behind: the one test that calls
``configure_logging`` restores global logging state afterwards.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest

import workflows.observability as obs
from workflows.observability import configure_logging, get_logger, log_operation


class TestGetLogger:
    """get_logger namespaces under the career_engine tree."""

    def test_namespaced_under_career_engine(self) -> None:
        assert get_logger("nodes").name == "career_engine.nodes"


class TestLogOperation:
    """log_operation times, escalates on slow, and logs+re-raises on error."""

    def test_ok_logs_elapsed_at_info(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = get_logger("t")
        with caplog.at_level(logging.INFO, logger="career_engine"):
            with log_operation("unit.op", logger=logger, foo="bar"):
                pass
        records = [r for r in caplog.records if "unit.op" in r.getMessage()]
        assert any(r.levelno == logging.INFO and "ok" in r.getMessage() for r in records)
        assert any("elapsed_ms=" in r.getMessage() for r in records)
        assert any("foo='bar'" in r.getMessage() for r in records)

    def test_slow_escalates_to_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = get_logger("t")
        # slow_ms=0 forces every operation to breach the budget.
        with caplog.at_level(logging.INFO, logger="career_engine"):
            with log_operation("slow.op", logger=logger, slow_ms=0):
                pass
        assert any(
            r.levelno == logging.WARNING and "slow" in r.getMessage()
            for r in caplog.records
        )

    def test_error_is_logged_and_reraised(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = get_logger("t")
        with caplog.at_level(logging.ERROR, logger="career_engine"):
            with pytest.raises(ValueError, match="boom"):
                with log_operation("fail.op", logger=logger):
                    raise ValueError("boom")
        assert any(
            r.levelno == logging.ERROR and "fail.op error" in r.getMessage()
            for r in caplog.records
        )


class TestConfigureLogging:
    """configure_logging is idempotent and does not add duplicate handlers."""

    @pytest.fixture()
    def _restore_logging(self) -> Iterator[None]:
        root = logging.getLogger("career_engine")
        before_handlers = list(root.handlers)
        before_propagate = root.propagate
        before_level = root.level
        before_flag = obs._configured
        adk_loggers = [logging.getLogger(n) for n in obs._ADK_ERROR_LOGGERS]
        before_adk_filters = {lg.name: list(lg.filters) for lg in adk_loggers}
        yield None
        # Restore: drop any handlers/filters we added, reset level/propagate + flag.
        for h in list(root.handlers):
            if h not in before_handlers:
                root.removeHandler(h)
        for lg in adk_loggers:
            for f in list(lg.filters):
                if f not in before_adk_filters[lg.name]:
                    lg.removeFilter(f)
        root.setLevel(before_level)
        root.propagate = before_propagate
        obs._configured = before_flag

    def test_idempotent_single_handler(self, _restore_logging: None) -> None:
        obs._configured = False
        root = logging.getLogger("career_engine")
        start = len(root.handlers)
        configure_logging(level=logging.INFO)
        configure_logging(level=logging.INFO)
        # Exactly one handler was added despite two calls.
        assert len(root.handlers) == start + 1

    def test_lowercase_string_level_does_not_crash(self, _restore_logging: None) -> None:
        """A lowercase level (e.g. CE_LOG_LEVEL=debug) is normalized, not fatal."""
        obs._configured = False
        configure_logging(level="debug")
        assert logging.getLogger("career_engine").level == logging.DEBUG


class TestDropHandledModelErrors:
    """The ADK-traceback filter drops only handled ModelAPIError records."""

    def _record(self, exc: BaseException | None) -> logging.LogRecord:
        exc_info = (type(exc), exc, None) if exc is not None else None
        return logging.LogRecord(
            "google_adk.x", logging.ERROR, "f", 1, "boom", None, exc_info
        )

    def test_drops_model_api_error(self) -> None:
        from integration.model_client import ModelAPIError

        filt = obs._DropHandledModelErrors()
        assert filt.filter(self._record(ModelAPIError("quota"))) is False

    def test_keeps_other_errors(self) -> None:
        filt = obs._DropHandledModelErrors()
        assert filt.filter(self._record(ValueError("real bug"))) is True

    def test_keeps_records_without_exception(self) -> None:
        filt = obs._DropHandledModelErrors()
        assert filt.filter(self._record(None)) is True


class TestMonitoredModelClient:
    """_get_model_client wraps the (possibly mocked) client with logging."""

    def test_delegates_and_logs_model_generate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from workflows import nodes

        calls: list[tuple[str, str, str]] = []

        class _FakeClient:
            def generate(self, model_id: str, system: str, user: str) -> str:
                calls.append((model_id, system, user))
                return "the-response"

        original = nodes._client_factory
        try:
            nodes.set_model_client_factory(lambda: _FakeClient())
            client: Any = nodes._get_model_client()
            with caplog.at_level(logging.INFO, logger="career_engine"):
                result = client.generate("model-x", "sys", "usr")
        finally:
            nodes.set_model_client_factory(original)

        assert result == "the-response"
        assert calls == [("model-x", "sys", "usr")]  # delegated unchanged
        assert any(
            "model.generate" in r.getMessage() and "model_id='model-x'" in r.getMessage()
            for r in caplog.records
        )
