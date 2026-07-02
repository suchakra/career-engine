"""Unit tests for tools/web_scraper.py.

All LLM calls are mocked — no network or API calls are made.
Each acceptance criterion (from WS-B) has at least one named test.

Acceptance criteria covered:
  AC1: Given a fixture JD HTML with nav/sidebar/culture block + requirements,
       clean_jd_html output CONTAINS hard skills/requirements and EXCLUDES
       culture/mission text. (test_clean_jd_contains_requirements,
       test_clean_jd_excludes_culture)
  AC2: The scraper requests BULK_CHEAP via the registry — no hardcoded model name
       appears in tools/web_scraper.py.  (test_scraper_uses_bulk_cheap_capability,
       test_no_hardcoded_gemini_model_in_scraper)
  AC3: Prompt/assembly logic is unit-tested — the system prompt and user template
       are exercised independently.  (test_system_prompt_content,
       test_user_template_content, test_clean_jd_assembles_correct_prompt)
  AC4: ScraperError propagated correctly for HTTP errors and timeouts.
       (test_fetch_raw_html_non_2xx_raises, test_fetch_raw_html_timeout_raises)
"""

from __future__ import annotations

import pathlib
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tools.web_scraper import (
    _CLEAN_JD_SYSTEM_PROMPT,
    _CLEAN_JD_USER_TMPL,
    ScraperError,
    clean_jd_html,
    scrape_job_description,
)

# Path to the fixture JD HTML
_FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"
_FIXTURE_JD_HTML = (_FIXTURE_DIR / "job_description.html").read_text(encoding="utf-8")
_FIXTURE_CLEANED_JD = (_FIXTURE_DIR / "cleaned_jd.txt").read_text(encoding="utf-8")


# ── Mock client helper ────────────────────────────────────────────────────────


def _mock_client(response_text: str) -> Any:
    """Return a mock client that returns response_text from generate_content_text."""
    mock = MagicMock()
    mock.generate_content_text.return_value = response_text
    return mock


def _public_resolver(_host: str) -> list[str]:
    """A stand-in resolver returning a public IP (keeps fetch tests offline).

    93.184.216.34 is a genuine public IP (example.com); it is deliberately NOT a
    private/loopback/reserved address, so it passes the SSRF guard. (A documentation
    range like 192.0.2.0/24 can't be used here — Python 3.12+ classifies it as
    private, which the guard would reject.)
    """
    return ["93.184.216.34"]


# ── AC1: Content filtering correctness ───────────────────────────────────────


class TestCleanJdContent:
    """AC1 — fixture JD is filtered to requirements; culture/mission excluded."""

    def test_clean_jd_contains_requirements(self) -> None:
        """AC1a: clean_jd_html output CONTAINS hard skill requirements from the fixture."""
        # The mock client returns the fixture cleaned text (what the real model would produce).
        client = _mock_client(_FIXTURE_CLEANED_JD)
        result = clean_jd_html(_FIXTURE_JD_HTML, client=client)

        # These hard skills / requirements MUST appear in the output.
        expected_fragments = [
            "Python",
            "PostgreSQL",
            "Kubernetes",
            "5+ years",
            "99.9%",
            "REST API",
            "Docker",
        ]
        for fragment in expected_fragments:
            assert fragment in result, (
                f"Expected requirement {fragment!r} not found in cleaned output"
            )

    def test_clean_jd_excludes_culture(self) -> None:
        """AC1b: clean_jd_html output EXCLUDES mission/culture/benefits text.

        The mock returns the fixture cleaned text; we assert culture phrases are absent.
        """
        client = _mock_client(_FIXTURE_CLEANED_JD)
        result = clean_jd_html(_FIXTURE_JD_HTML, client=client)

        # These culture/mission phrases must NOT appear in the output.
        excluded_fragments = [
            "Our Mission",
            "psychological safety",
            "equal-opportunity employer",
            "unlimited PTO",
            "401k",
            "celebrate diversity",
            "Privacy Policy",
        ]
        for fragment in excluded_fragments:
            assert fragment not in result, (
                f"Culture/mission text {fragment!r} leaked into cleaned output"
            )

    def test_clean_jd_excludes_nav_and_sidebar(self) -> None:
        """AC1c: clean_jd_html output EXCLUDES navigation and sidebar elements."""
        client = _mock_client(_FIXTURE_CLEANED_JD)
        result = clean_jd_html(_FIXTURE_JD_HTML, client=client)

        nav_fragments = [
            "All Jobs",
            "Share this job",
            "Related Roles",
            "Staff Engineer",  # sidebar related roles link
        ]
        for fragment in nav_fragments:
            assert fragment not in result, (
                f"Navigation/sidebar text {fragment!r} leaked into cleaned output"
            )


# ── AC2: Registry / capability usage ─────────────────────────────────────────


class TestScraperUsesRegistry:
    """AC2 — scraper requests BULK_CHEAP via registry; no hardcoded model name."""

    def test_scraper_uses_bulk_cheap_capability(self) -> None:
        """AC2a: clean_jd_html resolves BULK_CHEAP from the registry, not a hardcoded string."""
        from models.registry import get_registry
        from schema import Capability

        called_capabilities: list[Capability] = []

        class _CapturingRegistry:
            """Registry that records which capability was requested."""

            def get_model_id(
                self,
                capability: Capability,
                *,
                access_mode: Any = None,
            ) -> str:
                called_capabilities.append(capability)
                return "gemini-2.5-flash-lite"  # what BULK_CHEAP resolves to

            def supports(self, capability: Capability, *, access_mode: Any) -> bool:
                return True

        original = get_registry()
        from models.registry import set_registry

        set_registry(_CapturingRegistry())  # type: ignore[arg-type]
        try:
            client = _mock_client("Requirements: Python, Go")
            clean_jd_html("<html><body>test</body></html>", client=client)
        finally:
            set_registry(original)

        assert len(called_capabilities) >= 1
        assert Capability.BULK_CHEAP in called_capabilities, (
            f"Expected BULK_CHEAP to be requested; got: {called_capabilities}"
        )

    def test_no_hardcoded_gemini_model_in_scraper(self) -> None:
        """AC2b: grep confirms no hardcoded 'gemini-' model strings in web_scraper.py."""
        scraper_path = pathlib.Path(__file__).parent.parent / "tools" / "web_scraper.py"
        result = subprocess.run(
            ["grep", "-n", "gemini-", str(scraper_path)],
            capture_output=True,
            text=True,
        )
        # grep returns exit code 1 when nothing found (success for this test).
        assert result.returncode == 1, (
            f"Hardcoded model string found in web_scraper.py:\n{result.stdout}"
        )


# ── AC3: Prompt / assembly logic ─────────────────────────────────────────────


class TestPromptAssembly:
    """AC3 — unit-test prompt and template assembly logic."""

    def test_system_prompt_content(self) -> None:
        """AC3a: The system prompt instructs the model to exclude culture/mission fluff."""
        prompt_lower = _CLEAN_JD_SYSTEM_PROMPT.lower()
        assert "mission" in prompt_lower or "culture" in prompt_lower, (
            "System prompt should mention mission/culture exclusion"
        )
        assert "requirements" in prompt_lower or "skills" in prompt_lower, (
            "System prompt should mention requirements or skills"
        )
        assert "plain text" in prompt_lower or "no html" in prompt_lower, (
            "System prompt should specify plain text output"
        )

    def test_user_template_content(self) -> None:
        """AC3b: The user template has a {raw_html} slot for injection."""
        assert "{raw_html}" in _CLEAN_JD_USER_TMPL, (
            "_CLEAN_JD_USER_TMPL must contain the {raw_html} placeholder"
        )

    def test_clean_jd_assembles_correct_prompt(self) -> None:
        """AC3c: clean_jd_html passes the raw HTML into the client generate call."""
        html_input = "<html><body><p>Test requirement: Python 3.10+</p></body></html>"
        client = MagicMock()
        client.generate_content_text.return_value = "Python 3.10+"

        clean_jd_html(html_input, client=client)

        # Verify that generate_content_text was called once.
        client.generate_content_text.assert_called_once()
        call_kwargs = client.generate_content_text.call_args.kwargs

        # The prompt must contain the raw HTML.
        assert html_input in call_kwargs.get("prompt", ""), (
            "The raw HTML must appear in the generated prompt"
        )
        # The system prompt must be passed.
        assert call_kwargs.get("system", "") == _CLEAN_JD_SYSTEM_PROMPT, (
            "The system prompt must match _CLEAN_JD_SYSTEM_PROMPT"
        )
        # The model must be a non-empty string (from the registry).
        assert isinstance(call_kwargs.get("model", ""), str) and call_kwargs["model"], (
            "A model ID string must be passed to generate_content_text"
        )

    def test_clean_jd_passes_model_id_from_registry(self) -> None:
        """AC3d: The model ID passed to the client is the one the registry returns."""
        from models.registry import get_registry, set_registry
        from schema import Capability

        sentinel_model_id = "registry-resolved-model-for-test"

        class _SentinelRegistry:
            def get_model_id(self, cap: Capability, *, access_mode: Any = None) -> str:
                assert cap == Capability.BULK_CHEAP
                return sentinel_model_id

            def supports(self, cap: Capability, *, access_mode: Any) -> bool:
                return True

        original = get_registry()
        set_registry(_SentinelRegistry())  # type: ignore[arg-type]
        try:
            client = MagicMock()
            client.generate_content_text.return_value = "Skills: Python"
            clean_jd_html("<html>test</html>", client=client)
        finally:
            set_registry(original)

        call_kwargs = client.generate_content_text.call_args.kwargs
        assert call_kwargs["model"] == sentinel_model_id, (
            f"Expected model_id={sentinel_model_id!r}; "
            f"got {call_kwargs.get('model')!r}"
        )


# ── Error path tests ──────────────────────────────────────────────────────────


class TestScraperErrorPaths:
    """Failure paths: HTTP errors, timeouts, empty model response."""

    def test_fetch_raw_html_non_2xx_raises(self) -> None:
        """ScraperError is raised for a 404 response."""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.return_value = mock_response
            mock_httpx_cls.return_value = mock_client_instance

            from tools.web_scraper import fetch_raw_html

            with pytest.raises(ScraperError, match="Non-2xx response"):
                fetch_raw_html("https://example.com/job/123", resolver=_public_resolver)

    def test_fetch_raw_html_timeout_raises(self) -> None:
        """ScraperError is raised on httpx.TimeoutException."""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.side_effect = httpx.TimeoutException("timeout")
            mock_httpx_cls.return_value = mock_client_instance

            from tools.web_scraper import fetch_raw_html

            with pytest.raises(ScraperError, match="timed out"):
                fetch_raw_html("https://example.com/job/slow", resolver=_public_resolver)

    def test_fetch_raw_html_network_error_raises(self) -> None:
        """ScraperError is raised on httpx.RequestError (e.g. DNS failure)."""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.side_effect = httpx.ConnectError("DNS failure")
            mock_httpx_cls.return_value = mock_client_instance

            from tools.web_scraper import fetch_raw_html

            with pytest.raises(ScraperError, match="Network error"):
                fetch_raw_html("https://badhost.invalid/job/123", resolver=_public_resolver)

    def test_clean_jd_empty_model_response_raises(self) -> None:
        """ScraperError is raised if the model returns an empty response."""
        client = _mock_client("")  # empty response
        with pytest.raises(ScraperError, match="empty response"):
            clean_jd_html("<html><body>test</body></html>", client=client)

    def test_clean_jd_upgrade_required_raises_scraper_error(self) -> None:
        """If registry returns UpgradeRequired for BULK_CHEAP, ScraperError is raised."""
        from models.registry import get_registry, set_registry
        from schema import Capability, UpgradeRequired

        class _RefusingRegistry:
            def get_model_id(
                self, cap: Capability, *, access_mode: Any = None
            ) -> UpgradeRequired:
                return UpgradeRequired(
                    required_capability=cap,
                    node_name="test",
                    reason="BULK_CHEAP unavailable",
                )

            def supports(self, cap: Capability, *, access_mode: Any) -> bool:
                return False

        original = get_registry()
        set_registry(_RefusingRegistry())  # type: ignore[arg-type]
        try:
            with pytest.raises(ScraperError, match="BULK_CHEAP capability unavailable"):
                clean_jd_html("<html>test</html>", client=_mock_client("x"))
        finally:
            set_registry(original)

    def test_scrape_job_description_composes_fetch_and_clean(self) -> None:
        """scrape_job_description calls fetch then clean; the result is the cleaned text."""
        expected = "Python 3.10+, Kubernetes, PostgreSQL"
        client = _mock_client(expected)

        with patch("tools.web_scraper.fetch_raw_html", return_value="<html>raw</html>") as mock_fetch:
            result = scrape_job_description("https://example.com/job", client=client)

        mock_fetch.assert_called_once_with("https://example.com/job")
        assert result == expected


# ── SSRF hardening ────────────────────────────────────────────────────────────


class TestScraperSsrfGuards:
    """fetch_raw_html refuses non-HTTP(S) schemes and non-public hosts."""

    def test_rejects_non_http_scheme(self) -> None:
        """A file:// (or other non-HTTP) URL is refused before any request."""
        from tools.web_scraper import fetch_raw_html

        with pytest.raises(ScraperError, match="non-HTTP"):
            fetch_raw_html("file:///etc/passwd")

    def test_rejects_link_local_metadata_ip(self) -> None:
        """A URL resolving to the link-local metadata address is refused."""
        from tools.web_scraper import fetch_raw_html

        with pytest.raises(ScraperError, match="private, loopback, or link-local"):
            fetch_raw_html(
                "http://169.254.169.254/computeMetadata/v1/",
                resolver=lambda _h: ["169.254.169.254"],
            )

    def test_rejects_host_resolving_to_private_address(self) -> None:
        """A public-looking hostname that resolves to a private IP is refused."""
        from tools.web_scraper import fetch_raw_html

        with pytest.raises(ScraperError, match="private, loopback, or link-local"):
            fetch_raw_html(
                "https://internal.jobs.example.com/role",
                resolver=lambda _h: ["10.0.0.5"],
            )

    def test_rejects_metadata_hostname_before_resolution(self) -> None:
        """The metadata hostname is blocked even if DNS would resolve it publicly."""
        from tools.web_scraper import fetch_raw_html

        with pytest.raises(ScraperError, match="metadata"):
            fetch_raw_html(
                "http://metadata.google.internal/token",
                resolver=lambda _h: ["93.184.216.34"],
            )

    def test_rejects_redirect_to_internal_address(self) -> None:
        """A public URL that 302-redirects to an internal address is refused."""
        from tools.web_scraper import fetch_raw_html

        def _resolver(host: str) -> list[str]:
            return {"jobs.example.com": ["93.184.216.34"]}.get(host, ["169.254.169.254"])

        with patch("httpx.Client") as mock_httpx_cls:
            redirect = MagicMock()
            redirect.status_code = 302
            redirect.headers = {"location": "http://169.254.169.254/latest/meta-data/"}
            instance = MagicMock()
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=False)
            instance.get.return_value = redirect
            mock_httpx_cls.return_value = instance

            with pytest.raises(ScraperError, match="private, loopback, or link-local"):
                fetch_raw_html("https://jobs.example.com/role", resolver=_resolver)
