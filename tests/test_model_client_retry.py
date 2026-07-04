"""Tests for transient-error retry in the model client (503 UNAVAILABLE etc.)."""

from __future__ import annotations

import pytest

from integration import model_client as mc
from integration.model_client import _call_with_retry, _is_transient


class _ProviderError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class TestIsTransient:
    def test_503_by_code(self) -> None:
        assert _is_transient(_ProviderError("boom", code=503))

    def test_unavailable_by_message(self) -> None:
        assert _is_transient(
            _ProviderError("503 UNAVAILABLE. This model is currently experiencing high demand.")
        )

    def test_429_is_not_transient(self) -> None:
        assert not _is_transient(_ProviderError("429 RESOURCE_EXHAUSTED", code=429))

    def test_400_is_not_transient(self) -> None:
        assert not _is_transient(_ProviderError("400 invalid", code=400))


class TestCallWithRetry:
    def test_retries_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("integration.model_client.time.sleep", lambda _s: None)
        attempts = {"n": 0}

        def call() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _ProviderError("503 UNAVAILABLE", code=503)
            return "ok"

        assert _call_with_retry(call) == "ok"
        assert attempts["n"] == 3  # two transient failures, then success

    def test_gives_up_after_max_and_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("integration.model_client.time.sleep", lambda _s: None)
        attempts = {"n": 0}

        def call() -> str:
            attempts["n"] += 1
            raise _ProviderError("503 UNAVAILABLE", code=503)

        with pytest.raises(_ProviderError):
            _call_with_retry(call)
        assert attempts["n"] == mc._MAX_TRANSIENT_RETRIES

    def test_non_transient_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("integration.model_client.time.sleep", lambda _s: None)
        attempts = {"n": 0}

        def call() -> str:
            attempts["n"] += 1
            raise _ProviderError("429 RESOURCE_EXHAUSTED", code=429)

        with pytest.raises(_ProviderError):
            _call_with_retry(call)
        assert attempts["n"] == 1  # surfaced immediately, no retry
