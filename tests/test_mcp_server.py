"""Smoke tests for discovery/mcp_server.py — the FastMCP job server.

Verifies the two MCP tools are registered and that they adapt the shared contract
into JSON-serialisable payloads. The underlying fetch logic is covered in
tests/test_job_source.py; here we monkeypatch the source so no network is hit.
"""

from __future__ import annotations

import asyncio
from typing import Any

from discovery import job_source, mcp_server
from schema import JobMetadata, JobOpportunity, make_job_id


def _fake_search(directive: Any) -> list[JobOpportunity]:
    return [
        JobOpportunity(
            job_id=make_job_id("remotive", "1"),
            metadata=JobMetadata(title="Fractional CTO", company="Acme"),
            raw_description="text",
        )
    ]


def test_tools_are_registered() -> None:
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"search_jobs", "fetch_jd"} <= names


def test_search_jobs_returns_json_dicts(monkeypatch: Any) -> None:
    monkeypatch.setattr(job_source, "search_jobs", _fake_search)
    result = mcp_server.search_jobs(query="cto", desired_count=3)
    assert isinstance(result, list) and isinstance(result[0], dict)
    assert result[0]["metadata"]["title"] == "Fractional CTO"
    assert result[0]["match_status"] is None


def test_fetch_jd_delegates_to_source(monkeypatch: Any) -> None:
    monkeypatch.setattr(job_source, "fetch_job_description", lambda url: f"desc::{url}")
    assert mcp_server.fetch_jd("https://example.com/j/1") == "desc::https://example.com/j/1"
