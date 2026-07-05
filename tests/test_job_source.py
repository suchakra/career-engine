"""Unit tests for discovery/job_source.py — the MCP server's data layer.

All network I/O is injected (``fetch_json`` / ``fetch_text``): no live HTTP, no
keys. Covers normalisation into the JobOpportunity contract, idempotent job_ids,
deterministic client-side filtering, HTML stripping, and the SSRF guard on the
caller-controlled fetch_jd path.
"""

from __future__ import annotations

from typing import Any

import pytest

from discovery import job_source
from discovery.job_source import (
    SOURCE,
    fetch_job_description,
    search_jobs,
)
from schema import EmploymentType, ScoutDirective, WorkModel, make_job_id
from tools.web_scraper import ScraperError

# A canned Remotive-shaped payload (the real API returns this envelope).
_REMOTIVE_PAYLOAD: dict[str, Any] = {
    "jobs": [
        {
            "id": 101,
            "url": "https://remotive.com/jobs/101",
            "title": "Fractional CTO (AI Platform)",
            "company_name": "Acme AI",
            "candidate_required_location": "Worldwide",
            "job_type": "contract",
            "description": "<p>Lead <b>AWS</b> infra &amp; multi-agent orchestration.</p>",
        },
        {
            "id": 102,
            "url": "https://remotive.com/jobs/102",
            "title": "Engineering Director",
            "company_name": "Legacy Corp",
            "candidate_required_location": "USA",
            "job_type": "full_time",
            "description": "<div>Manage a large org. On-site required.</div>",
        },
        {
            "id": 103,
            "url": "https://remotive.com/jobs/103",
            "title": "Principal Engineer",
            "company_name": "Startup Labs",
            "candidate_required_location": "Europe",
            "job_type": "full_time",
            "description": "Autonomous pipelines, Podman sandboxing.",
        },
    ]
}


def _fetch_json(_url: str) -> dict[str, Any]:
    return _REMOTIVE_PAYLOAD


class TestSearchNormalisation:
    def test_maps_fields_into_contract(self) -> None:
        jobs = search_jobs(ScoutDirective(query="cto", desired_count=5), fetch_json=_fetch_json)
        first = next(j for j in jobs if j.metadata.company == "Acme AI")
        assert first.job_id == make_job_id(SOURCE, "101")
        assert first.metadata.title == "Fractional CTO (AI Platform)"
        assert first.metadata.work_model is WorkModel.REMOTE
        assert first.metadata.employment_type is EmploymentType.CONTRACT
        assert first.metadata.url == "https://remotive.com/jobs/101"
        # HTML stripped + entities unescaped, no markup leaks through.
        assert "AWS" in first.raw_description and "<" not in first.raw_description
        assert "&amp;" not in first.raw_description
        # The Scout never classifies — that's the Primary's job.
        assert first.match_status is None

    def test_job_id_is_idempotent(self) -> None:
        a = search_jobs(ScoutDirective(query="cto", desired_count=5), fetch_json=_fetch_json)
        b = search_jobs(ScoutDirective(query="cto", desired_count=5), fetch_json=_fetch_json)
        assert [j.job_id for j in a] == [j.job_id for j in b]

    def test_unknown_job_type_stays_unknown(self) -> None:
        payload = {"jobs": [{"id": 9, "title": "X", "company_name": "Y", "job_type": "gig"}]}
        jobs = search_jobs(ScoutDirective(query="x"), fetch_json=lambda _u: payload)
        assert jobs[0].metadata.employment_type is EmploymentType.UNKNOWN


class TestFiltering:
    def test_exclude_company_dropped(self) -> None:
        jobs = search_jobs(
            ScoutDirective(query="eng", desired_count=5, exclude_companies=["legacy corp"]),
            fetch_json=_fetch_json,
        )
        assert all(j.metadata.company != "Legacy Corp" for j in jobs)

    def test_exclude_keyword_dropped(self) -> None:
        jobs = search_jobs(
            ScoutDirective(query="eng", desired_count=5, exclude_keywords=["on-site"]),
            fetch_json=_fetch_json,
        )
        assert all("on-site" not in j.raw_description.lower() for j in jobs)

    def test_include_keyword_is_soft_and(self) -> None:
        jobs = search_jobs(
            ScoutDirective(query="eng", desired_count=5, include_keywords=["Podman"]),
            fetch_json=_fetch_json,
        )
        assert len(jobs) == 1 and jobs[0].metadata.company == "Startup Labs"

    def test_desired_count_caps_results(self) -> None:
        jobs = search_jobs(ScoutDirective(query="eng", desired_count=1), fetch_json=_fetch_json)
        assert len(jobs) == 1

    def test_empty_payload_returns_empty(self) -> None:
        jobs = search_jobs(ScoutDirective(query="x"), fetch_json=lambda _u: {})
        assert jobs == []


class TestSearchUrl:
    def test_query_is_url_encoded_and_host_fixed(self) -> None:
        captured: dict[str, str] = {}

        def _spy(url: str) -> dict[str, Any]:
            captured["url"] = url
            return {"jobs": []}

        search_jobs(ScoutDirective(query="fractional cto & ai"), fetch_json=_spy)
        assert captured["url"].startswith("https://remotive.com/api/remote-jobs?search=")
        assert "fractional+cto" in captured["url"]  # space encoded, host not attacker-controlled


class TestFetchJd:
    def test_strips_html(self) -> None:
        text = fetch_job_description(
            "https://remotive.com/jobs/101",
            fetch_text=lambda _u: "<h1>Role</h1><p>Do &amp; know things.</p>",
        )
        assert text == "Role Do & know things."

    def test_ssrf_guard_blocks_private_address(self) -> None:
        # Drive the real default fetcher but inject a resolver that maps the host
        # to a private IP — the SSRF guard must reject it before any HTTP call.
        def _private_fetch(url: str) -> str:
            return job_source._default_fetch_text(url, resolver=lambda _h: ["127.0.0.1"])

        with pytest.raises(ScraperError):
            fetch_job_description("http://internal.example/jobs/1", fetch_text=_private_fetch)
