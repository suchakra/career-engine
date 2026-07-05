"""Live job-source adapter — the data layer behind the MCP server's tools.

This module is the pure, injectable logic exposed by the two MCP tools
(``search_jobs`` and ``fetch_jd``). It talks to **Remotive**, a live public
job board whose read API needs **no key** (so the demo carries no secrets), and
normalises each posting into the shared :class:`schema.JobOpportunity` contract
(stamping a stable :func:`schema.make_job_id` for idempotency).

Security posture (the MCP server is the sandbox boundary):

- ``search_jobs`` only ever hits a **fixed** source host; the caller controls the
  query string (URL-encoded), never the host or scheme.
- ``fetch_jd`` takes a fully caller-controlled URL, so it reuses the scraper's
  SSRF guard (:func:`tools.web_scraper._assert_safe_url`) — an attacker-supplied
  URL can never reach a private / loopback / cloud-metadata address.

Everything network-facing is injected (``fetch_json`` / ``fetch_text``) so the
whole module is unit-testable offline, with no keys and no live HTTP.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx

from schema import (
    EmploymentType,
    JobMetadata,
    JobOpportunity,
    ScoutDirective,
    WorkModel,
    make_job_id,
)
from tools.web_scraper import (
    ScraperError,
    _assert_safe_url,
    _resolve_addresses,
)

# ── Source config ─────────────────────────────────────────────────────────────

SOURCE: str = "remotive"
"""Stable source tag folded into every ``job_id`` (see :func:`schema.make_job_id`)."""

_REMOTIVE_SEARCH_URL: str = "https://remotive.com/api/remote-jobs"
"""Fixed, key-free public job-board endpoint. Only the query string varies."""

_FETCH_TIMEOUT_SECONDS: float = 20.0
_RESULT_CAP: int = 25
"""Absolute ceiling on postings pulled per search (bounds cost + payload size)."""

# Remotive ``job_type`` → our EmploymentType. Anything unmapped stays UNKNOWN so
# the Primary never over-claims a fact the source didn't assert.
_JOB_TYPE_MAP: dict[str, EmploymentType] = {
    "full_time": EmploymentType.FULL_TIME,
    "contract": EmploymentType.CONTRACT,
    "freelance": EmploymentType.CONTRACT,
    "part_time": EmploymentType.PART_TIME,
    "internship": EmploymentType.PART_TIME,
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Injectable network seams (default to guarded, real HTTP).
JsonFetcher = Callable[[str], Any]
TextFetcher = Callable[[str], str]


# ── HTML → text ───────────────────────────────────────────────────────────────


def _strip_html(html: str) -> str:
    """Collapse an HTML fragment to readable plain text (Remotive returns HTML).

    Tags are removed and entities unescaped; the model never sees raw markup and
    the value is never rendered as HTML downstream.
    """
    text = unescape(_TAG_RE.sub(" ", html))
    return _WS_RE.sub(" ", text).strip()


def _employment_type(job_type: str) -> EmploymentType:
    """Map a Remotive ``job_type`` string to our :class:`EmploymentType`."""
    return _JOB_TYPE_MAP.get(job_type.strip().lower(), EmploymentType.UNKNOWN)


def _to_job(raw: dict[str, Any]) -> JobOpportunity:
    """Normalise one Remotive posting dict into a :class:`JobOpportunity`.

    ``job_id`` is derived from the source + the posting's external id so a
    crash/restart of the loop never duplicates a record (idempotency).
    """
    external_id = str(raw.get("id", "")).strip()
    return JobOpportunity(
        job_id=make_job_id(SOURCE, external_id),
        metadata=JobMetadata(
            title=str(raw.get("title", "")),
            company=str(raw.get("company_name", "")),
            # Remotive is a remote-only board — every posting is remote-eligible.
            work_model=WorkModel.REMOTE,
            employment_type=_employment_type(str(raw.get("job_type", ""))),
            location=str(raw.get("candidate_required_location", "")),
            url=str(raw.get("url", "")),
        ),
        raw_description=_strip_html(str(raw.get("description", ""))),
    )


# ── Client-side filtering (deterministic, testable) ───────────────────────────


def _passes_filters(job: JobOpportunity, directive: ScoutDirective) -> bool:
    """Apply the directive's deterministic exclude/include filters to a posting.

    The source query is fuzzy; these filters make the Scout's output precise and
    let the Primary's loop refine deterministically across iterations.
    """
    company = job.metadata.company.strip().lower()
    if any(company == c.strip().lower() for c in directive.exclude_companies if c.strip()):
        return False

    haystack = f"{job.metadata.title}\n{job.raw_description}".lower()
    if any(kw.strip().lower() in haystack for kw in directive.exclude_keywords if kw.strip()):
        return False
    # include_keywords act as a soft AND when present (all must appear somewhere).
    includes = [kw.strip().lower() for kw in directive.include_keywords if kw.strip()]
    return all(kw in haystack for kw in includes)


# ── Default (guarded) network fetchers ────────────────────────────────────────


def _guarded_get(url: str, *, resolver: Callable[[str], list[str]]) -> httpx.Response:
    """Fetch ``url`` with the SSRF guard applied first, then a 2xx check.

    Shared by the JSON (search) and text (fetch_jd) default fetchers.
    """
    _assert_safe_url(url, resolver=resolver)
    try:
        with httpx.Client(follow_redirects=False, timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = client.get(url)
    except httpx.TimeoutException as exc:
        raise ScraperError(f"Request timed out fetching {url!r}: {exc}") from exc
    except httpx.RequestError as exc:
        raise ScraperError(f"Network error fetching {url!r}: {exc}") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise ScraperError(f"Non-2xx response fetching {url!r}: HTTP {response.status_code}")
    return response


def _default_fetch_json(url: str, *, resolver: Callable[[str], list[str]] = _resolve_addresses) -> Any:
    """Guarded GET returning parsed JSON (default search fetcher)."""
    return _guarded_get(url, resolver=resolver).json()


def _default_fetch_text(url: str, *, resolver: Callable[[str], list[str]] = _resolve_addresses) -> str:
    """Guarded GET returning response text (default fetch_jd fetcher)."""
    return _guarded_get(url, resolver=resolver).text


# ── Public API (the MCP tools' logic) ─────────────────────────────────────────


def search_jobs(
    directive: ScoutDirective,
    *,
    fetch_json: JsonFetcher = _default_fetch_json,
) -> list[JobOpportunity]:
    """Fetch fresh postings for a directive and normalise them to JobOpportunity.

    The Scout calls this (through the MCP server). The directive's ``query`` drives
    the source search; ``exclude_*`` / ``include_keywords`` are applied client-side
    for deterministic precision; results are capped at ``desired_count`` (and never
    exceed :data:`_RESULT_CAP`).

    Args:
        directive: The structured search instruction from the Primary.
        fetch_json: Injectable JSON fetcher (defaults to the SSRF-guarded HTTP one).

    Returns:
        Up to ``directive.desired_count`` matching :class:`JobOpportunity` objects
        (empty ``match_status`` — the Primary classifies them later).

    Raises:
        ScraperError: on an unsafe URL, network failure, or non-2xx response.
    """
    want = max(1, directive.desired_count)
    # Over-fetch a little so client-side filtering can still meet the quota.
    limit = min(_RESULT_CAP, want * 3)
    url = f"{_REMOTIVE_SEARCH_URL}?search={quote_plus(directive.query)}&limit={limit}"

    payload = fetch_json(url)
    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []

    out: list[JobOpportunity] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        # Without a stable external id, make_job_id would hash an empty string and
        # collapse every id-less posting onto one job_id → dedup + ledger collisions.
        if not str(raw.get("id", "")).strip():
            continue
        job = _to_job(raw)
        if job.job_id in seen or not _passes_filters(job, directive):
            continue
        seen.add(job.job_id)
        out.append(job)
        if len(out) >= want:
            break
    return out


def fetch_job_description(
    url: str,
    *,
    fetch_text: TextFetcher = _default_fetch_text,
) -> str:
    """Fetch and clean the plain-text job description at a posting URL.

    The URL is fully caller-controlled, so the default fetcher applies the SSRF
    guard before any request. Returns readable text (HTML stripped).

    Args:
        url: The posting URL (validated against the SSRF guard by the default fetcher).
        fetch_text: Injectable text fetcher (defaults to the SSRF-guarded HTTP one).

    Returns:
        The posting body as plain text.

    Raises:
        ScraperError: on an unsafe URL, network failure, or non-2xx response.
    """
    return _strip_html(fetch_text(url))
