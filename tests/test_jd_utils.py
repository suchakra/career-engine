"""Tests for web.jd_utils — JD metadata extraction (9G)."""

from __future__ import annotations

from unittest.mock import MagicMock

from web.jd_utils import extract_jd_metadata


def test_extract_jd_metadata_returns_title_company() -> None:
    """Fake client returns valid JSON; assert title and company are returned."""
    client = MagicMock()
    client.generate.return_value = '{"title": "SWE", "company": "Acme"}'
    title, company = extract_jd_metadata("Some JD text", client, "gemini-2.5-flash-lite")
    assert title == "SWE"
    assert company == "Acme"


def test_extract_jd_metadata_handles_malformed_json() -> None:
    """Fake client returns non-JSON; assert ("", "") is returned without raising."""
    client = MagicMock()
    client.generate.return_value = "oops"
    result = extract_jd_metadata("Some JD text", client, "gemini-2.5-flash-lite")
    assert result == ("", "")


def test_extract_jd_metadata_truncates_long_jd() -> None:
    """JD text of 4000 chars is truncated to at most 3000 chars before LLM call."""
    client = MagicMock()
    client.generate.return_value = '{"title": "", "company": ""}'
    jd_text = "x" * 4000
    extract_jd_metadata(jd_text, client, "gemini-2.5-flash-lite")
    _model_id, _system, user_arg = client.generate.call_args[0]
    assert len(user_arg) <= 3000


def test_extract_jd_metadata_null_fields_return_empty_string() -> None:
    """JSON null for title/company returns ('', '') not ('None', 'None')."""
    client = MagicMock()
    client.generate.return_value = '{"title": null, "company": null}'
    title, company = extract_jd_metadata("Some JD text", client, "gemini-2.5-flash-lite")
    assert title == ""
    assert company == ""


def test_extract_jd_metadata_strips_markdown_fences() -> None:
    """Handles model output wrapped in markdown code fences."""
    client = MagicMock()
    client.generate.return_value = '```json\n{"title": "SWE", "company": "Acme"}\n```'
    title, company = extract_jd_metadata("Some JD text", client, "gemini-2.5-flash-lite")
    assert title == "SWE"
    assert company == "Acme"
