"""Unit tests for discovery/scout.py — the stateless Fetcher agent.

Covers delegation to the MCP tool client and the real in-process MCP dispatch
path (InProcessMcpClient), with the job source monkeypatched so no network is hit.
"""

from __future__ import annotations

from typing import Any

import pytest

from discovery import job_source
from discovery.scout import InProcessMcpClient, JobToolClient, Scout
from schema import JobMetadata, JobOpportunity, ScoutDirective, make_job_id

pytestmark = pytest.mark.asyncio


def _canned(directive: ScoutDirective) -> list[JobOpportunity]:
    return [
        JobOpportunity(
            job_id=make_job_id("remotive", "1"),
            metadata=JobMetadata(title="Fractional CTO", company="Acme", url="https://x/1"),
            raw_description=f"desc for {directive.query}",
        )
    ]


class _FakeTools:
    """A minimal JobToolClient double recording the last directive."""

    def __init__(self) -> None:
        self.last_directive: ScoutDirective | None = None

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        self.last_directive = directive
        return _canned(directive)

    async def fetch_jd(self, url: str) -> str:
        return f"jd::{url}"


async def test_fake_tools_satisfies_protocol() -> None:
    assert isinstance(_FakeTools(), JobToolClient)


async def test_scout_delegates_fetch_to_tools() -> None:
    tools = _FakeTools()
    scout = Scout(tools=tools)
    jobs = await scout.fetch(ScoutDirective(query="cto", desired_count=3))
    assert len(jobs) == 1 and jobs[0].metadata.company == "Acme"
    assert tools.last_directive is not None and tools.last_directive.query == "cto"


async def test_scout_fetch_description_delegates() -> None:
    scout = Scout(tools=_FakeTools())
    assert await scout.fetch_description("https://x/1") == "jd::https://x/1"


async def test_scout_is_stateless_across_directives() -> None:
    scout = Scout(tools=_FakeTools())
    a = await scout.fetch(ScoutDirective(query="one"))
    b = await scout.fetch(ScoutDirective(query="two"))
    assert a[0].raw_description == "desc for one"
    assert b[0].raw_description == "desc for two"


async def test_in_process_client_round_trips_through_real_mcp(monkeypatch: Any) -> None:
    # Drive the REAL FastMCP tool dispatch, but stub the network source so the
    # test is offline. The client must revalidate the tool output into the contract.
    monkeypatch.setattr(job_source, "search_jobs", _canned)
    client = InProcessMcpClient()  # binds to discovery.mcp_server.mcp
    scout = Scout(tools=client)
    jobs = await scout.fetch(ScoutDirective(query="cto", desired_count=2))
    assert len(jobs) == 1
    assert isinstance(jobs[0], JobOpportunity)
    assert jobs[0].metadata.title == "Fractional CTO"
    assert jobs[0].match_status is None


async def test_in_process_client_fetch_jd(monkeypatch: Any) -> None:
    monkeypatch.setattr(job_source, "fetch_job_description", lambda url: f"body::{url}")
    client = InProcessMcpClient()
    assert await client.fetch_jd("https://x/9") == "body::https://x/9"
