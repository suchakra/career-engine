"""CareerEngine job-discovery MCP server (FastMCP, stdio).

A **real, separate-process** Model Context Protocol server that exposes the job
board as two sandboxed tools:

- ``search_jobs`` — fetch fresh postings for a structured query.
- ``fetch_jd``   — fetch the full plain-text description at a posting URL.

The Scout agent connects to this server as an MCP *client* (e.g. ADK's
``MCPToolset`` over stdio). Keeping the fetch behind an MCP boundary is the
security seam: the untrusted network I/O lives in this process (SSRF-guarded,
and Podman-sandboxable on the roadmap), never inside the agent's reasoning loop.

Run it directly:  ``python -m discovery.mcp_server``  (speaks MCP over stdio).

The heavy lifting lives in :mod:`discovery.job_source` (pure + unit-tested); the
tools here are intentionally thin adapters that (de)serialise the shared contract.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from discovery import job_source
from schema import ScoutDirective

mcp = FastMCP("career-engine-jobs")


@mcp.tool()
def search_jobs(
    query: str,
    desired_count: int = 5,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    exclude_companies: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search a live job board and return normalised postings.

    Args:
        query: Free-text role focus (e.g. "fractional CTO cloud AI").
        desired_count: Target number of fresh matches (>=1).
        include_keywords: Terms that must all appear in a posting (soft AND).
        exclude_keywords: Terms that disqualify a posting if present.
        exclude_companies: Companies to drop (case-insensitive exact match).

    Returns:
        A list of JobOpportunity dicts (JSON-mode) with empty ``match_status`` —
        the Primary agent classifies them after fetch.
    """
    directive = ScoutDirective(
        query=query,
        desired_count=max(1, desired_count),
        include_keywords=include_keywords or [],
        exclude_keywords=exclude_keywords or [],
        exclude_companies=exclude_companies or [],
    )
    return [job.model_dump(mode="json") for job in job_source.search_jobs(directive)]


@mcp.tool()
def fetch_jd(url: str) -> str:
    """Fetch the full plain-text job description at a posting URL (SSRF-guarded)."""
    return job_source.fetch_job_description(url)


def main() -> None:
    """Run the MCP server over stdio (blocking)."""
    mcp.run()


if __name__ == "__main__":
    main()
