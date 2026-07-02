"""Tests for graceful model API-error handling (quota/429 → typed, not a crash)."""

from __future__ import annotations

from typing import Any

import pytest

from cli.app import format_model_api_error
from integration.model_client import (
    GeminiModelClient,
    ModelAPIError,
    _as_model_api_error,
)


class _RateLimitError(Exception):
    """Mimics a google.genai ClientError(429) with a retry hint in its message."""

    code = 429

    def __str__(self) -> str:
        return "429 RESOURCE_EXHAUSTED. Quota exceeded. Please retry in 25s."


class _ServerError(Exception):
    code = 500

    def __str__(self) -> str:
        return "500 INTERNAL"


class TestTranslation:
    def test_detects_rate_limit_status_and_retry(self) -> None:
        err = _as_model_api_error(_RateLimitError())
        assert err.is_rate_limited is True
        assert err.status_code == 429
        assert err.retry_after_seconds == 25.0

    def test_non_rate_limit_error_is_not_flagged(self) -> None:
        err = _as_model_api_error(_ServerError())
        assert err.is_rate_limited is False
        assert err.status_code == 500
        assert err.retry_after_seconds is None


class TestWrapping:
    def test_generate_wraps_provider_error_as_model_api_error(self) -> None:
        client = GeminiModelClient.__new__(GeminiModelClient)  # bypass real genai client

        class _Models:
            def generate_content(self, **_: Any) -> Any:
                raise _RateLimitError()

        class _FakeClient:
            models = _Models()

        client._client = _FakeClient()  # type: ignore[assignment]
        with pytest.raises(ModelAPIError) as ei:
            client.generate(model_id="m", system="s", user="u")
        assert ei.value.is_rate_limited is True


class TestFriendlyMessage:
    def test_rate_limited_message_is_actionable(self) -> None:
        err = ModelAPIError(
            "Gemini quota", status_code=429, retry_after_seconds=25.0, is_rate_limited=True
        )
        msg = format_model_api_error(err, use_firestore=True)
        assert "rate limit" in msg.lower()
        assert "25" in msg
        assert "--firestore" in msg

    def test_generic_error_message_is_not_a_stack_trace(self) -> None:
        err = ModelAPIError("Model API call failed: boom", status_code=500)
        msg = format_model_api_error(err, use_firestore=False)
        assert "Model API error" in msg
        assert "Traceback" not in msg
