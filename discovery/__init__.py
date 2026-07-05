"""Two-agent (A2A) job-discovery feature.

Package layout (one feature, one package):

- :mod:`discovery.job_source` — the pure, injectable data layer behind the MCP
  server's tools: it talks to a live, key-free public job board and normalises
  postings into the shared :class:`schema.JobOpportunity` contract.
- :mod:`discovery.mcp_server` — a real (separate-process) FastMCP server that
  exposes ``search_jobs`` and ``fetch_jd`` as MCP tools over stdio.

The Scout agent (stateless Fetcher) is the MCP *client*; the MCP *server* is the
sandboxed data-access boundary that isolates untrusted remote fetches from the
agent process (SSRF-guarded today; Podman-sandboxed on the roadmap).

Naming note: this package is deliberately **not** called ``mcp`` — a top-level
``mcp/`` directory would shadow the installed ``mcp`` SDK on ``sys.path``.
"""
