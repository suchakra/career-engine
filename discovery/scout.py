"""Scout agent — the stateless Fetcher half of the two-agent A2A loop.

The Scout turns a structured :class:`schema.ScoutDirective` into a batch of
:class:`schema.JobOpportunity` objects by calling the MCP job server's tools. It
is deliberately **stateless**: every directive is self-contained and the Scout
keeps no memory between fetches, so it can be scaled/replaced freely and — in the
multi-user vision — a single stateless Scout fleet can serve many stateful
Primaries.

Access discipline (the point of the MCP boundary): the Scout reaches job data
**only** through the MCP tool surface (:class:`JobToolClient`), never by importing
:mod:`discovery.job_source` directly. That keeps the untrusted network fetch behind
the server's security seam (SSRF guard today, Podman sandbox on the roadmap).

Transports:

- :class:`InProcessMcpClient` — dispatches through the real FastMCP tool machinery
  in-process (validation + serialisation), needing no subprocess or key. This is
  the default for the CLI demo and for tests.
- A stdio subprocess client (spawning ``python -m discovery.mcp_server``) is the
  roadmap transport for a fully out-of-process / network A2A deployment.

Model routing note: the Scout needs no inference for the P0 fetch — filtering is
deterministic in the MCP tool. Flash-assisted *relevance triage* (cheap bulk
pre-filter before the Pro-tier Primary) is a roadmap enhancement; the model client
seam is injected here so it can be added without a contract change.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from schema import JobOpportunity, ScoutDirective


@runtime_checkable
class JobToolClient(Protocol):
    """The MCP tool surface the Scout depends on (search + fetch)."""

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        """Fetch a batch of normalised postings for a directive."""
        ...

    async def fetch_jd(self, url: str) -> str:
        """Fetch the full plain-text description at a posting URL."""
        ...


class InProcessMcpClient:
    """A :class:`JobToolClient` that calls a FastMCP app's tools in-process.

    Uses ``FastMCP.call_tool``, so requests go through the genuine MCP tool
    dispatch (argument validation + structured (de)serialisation) — it is a real
    MCP client interaction, just without a subprocess/stdio transport. This keeps
    the demo and tests key-free while preserving the tool-mediated boundary.
    """

    def __init__(self, app: Any | None = None) -> None:
        """Bind to a FastMCP app (defaults to the discovery job server)."""
        if app is None:
            from discovery.mcp_server import mcp

            app = mcp
        self._app: Any = app

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke an MCP tool and return its structured ``result`` payload."""
        result = await self._app.call_tool(name, arguments)
        # FastMCP returns (content_blocks, {"result": <value>}).
        structured = result[1] if isinstance(result, tuple) else result
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        return structured

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        """Call the ``search_jobs`` MCP tool and revalidate into the contract."""
        raw = await self._call(
            "search_jobs",
            {
                "query": directive.query,
                "desired_count": directive.desired_count,
                "include_keywords": directive.include_keywords,
                "exclude_keywords": directive.exclude_keywords,
                "exclude_companies": directive.exclude_companies,
            },
        )
        items = raw if isinstance(raw, list) else []
        return [JobOpportunity.model_validate(item) for item in items]

    async def fetch_jd(self, url: str) -> str:
        """Call the ``fetch_jd`` MCP tool and return the description text."""
        raw = await self._call("fetch_jd", {"url": url})
        return str(raw)


class Scout:
    """Stateless Fetcher: a ScoutDirective in, a JobOpportunity batch out.

    Holds only a reference to the MCP tool client — no per-session memory, so the
    same Scout instance can serve unrelated directives back-to-back.
    """

    def __init__(self, tools: JobToolClient | None = None) -> None:
        """Bind the Scout to an MCP tool client (defaults to the in-process one)."""
        self._tools: JobToolClient = tools if tools is not None else InProcessMcpClient()

    async def fetch(self, directive: ScoutDirective) -> list[JobOpportunity]:
        """Fetch one batch of postings for ``directive`` via the MCP server.

        Args:
            directive: The self-contained search instruction from the Primary.

        Returns:
            The fetched postings (empty ``match_status`` — the Primary classifies).
        """
        return await self._tools.search_jobs(directive)

    async def fetch_description(self, url: str) -> str:
        """Fetch the full description for a single posting URL via the MCP server."""
        return await self._tools.fetch_jd(url)
