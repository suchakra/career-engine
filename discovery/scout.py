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

Transports (both real MCP client↔server interactions):

- :class:`InProcessMcpClient` — dispatches through the real FastMCP tool machinery
  in-process (validation + serialisation), needing no subprocess or key. This is
  the default for the CLI demo and for tests.
- :class:`StdioMcpClient` — spawns the MCP server as a **separate process**
  (``python -m discovery.mcp_server``) and talks to it over the MCP **stdio**
  transport — genuine out-of-process A2A (the shape a networked/sandboxed
  deployment takes). Same :class:`JobToolClient` surface, so it drops into the
  Scout unchanged.

Model routing note: the Scout needs no inference for the P0 fetch — filtering is
deterministic in the MCP tool. Flash-assisted *relevance triage* (cheap bulk
pre-filter before the Pro-tier Primary) is a roadmap enhancement; the model client
seam is injected here so it can be added without a contract change.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from schema import JobOpportunity, ScoutDirective


def _search_args(directive: ScoutDirective) -> dict[str, Any]:
    """Map a ScoutDirective to the ``search_jobs`` MCP tool arguments."""
    return {
        "query": directive.query,
        "desired_count": directive.desired_count,
        "include_keywords": directive.include_keywords,
        "exclude_keywords": directive.exclude_keywords,
        "exclude_companies": directive.exclude_companies,
    }


def _jobs_from_raw(raw: Any) -> list[JobOpportunity]:
    """Revalidate a tool's raw list payload into JobOpportunity objects."""
    items = raw if isinstance(raw, list) else []
    return [JobOpportunity.model_validate(item) for item in items]


def _structured_payload(result: Any) -> Any:
    """Extract a tool's structured ``result`` value.

    Handles both transports: FastMCP in-process returns ``(content, {"result": …})``;
    the stdio ``ClientSession`` returns a ``CallToolResult`` with ``.structuredContent``.
    """
    structured = result[1] if isinstance(result, tuple) else getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    return structured


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
        return _structured_payload(await self._app.call_tool(name, arguments))

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        """Call the ``search_jobs`` MCP tool and revalidate into the contract."""
        return _jobs_from_raw(await self._call("search_jobs", _search_args(directive)))

    async def fetch_jd(self, url: str) -> str:
        """Call the ``fetch_jd`` MCP tool and return the description text."""
        return str(await self._call("fetch_jd", {"url": url}))


class StdioMcpClient:
    """A :class:`JobToolClient` that talks to the MCP server as a SEPARATE PROCESS.

    Spawns ``python -m discovery.mcp_server`` and calls its tools over the MCP
    **stdio** transport — a genuine out-of-process client↔server round-trip (vs
    :class:`InProcessMcpClient`'s in-process dispatch), the shape a networked or
    Podman-sandboxed deployment takes. A fresh session is opened per call (simple +
    correct); a persistent session is a future optimisation.
    """

    def __init__(self, *, command: str | None = None, args: Sequence[str] | None = None) -> None:
        """Bind the launch command (defaults to this interpreter + the server module)."""
        self._command = command or sys.executable
        self._args = list(args) if args is not None else ["-m", "discovery.mcp_server"]

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        """Spawn the server, initialise a stdio session, call the tool, and extract."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=self._command, args=self._args)
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
        return _structured_payload(result)

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        """Call the ``search_jobs`` tool over stdio and revalidate into the contract."""
        return _jobs_from_raw(await self._call("search_jobs", _search_args(directive)))

    async def fetch_jd(self, url: str) -> str:
        """Call the ``fetch_jd`` tool over stdio and return the description text."""
        return str(await self._call("fetch_jd", {"url": url}))


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
