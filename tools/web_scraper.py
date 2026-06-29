"""Two-step job-description scraper.

Phase 1 implementation (WS-B).

Step 1: fetch_raw_html(url) fetches raw HTML via httpx; handles timeouts and
    non-2xx responses with ScraperError.
Step 2: clean_jd_html(html, client) uses a BULK_CHEAP model (resolved via the
    registry — never hardcoded) to strip navigation, sidebars, and
    mission/culture fluff, returning only functional requirements and hard skills.

Design rules (enforced):
- The LLM client is injectable so tests can mock it without network calls.
- The scraper requests BULK_CHEAP capability via the registry; it never
  names a model directly.
- Model output is treated as untrusted text; it is NOT rendered as HTML.
- Returns a plain string suitable for further processing.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from models.registry import get_registry
from schema import Capability

# ── Constants ─────────────────────────────────────────────────────────────────

_FETCH_TIMEOUT_SECONDS: float = 20.0

_CLEAN_JD_SYSTEM_PROMPT = """\
You are a job-description parser.  Your task is to extract only the
functional requirements and hard technical skills from a raw HTML job posting.

Output rules (mandatory):
- Output ONLY plain text — no HTML, no Markdown, no bullet-symbol characters.
- Include: required skills, preferred skills, responsibilities, qualifications,
  years of experience, and technology stack.
- Exclude: company mission/vision, culture/values paragraphs, benefits, DEI
  statements, equal-opportunity boilerplate, navigation menus, sidebars, headers,
  footers, and any text that does not describe what the candidate must DO or KNOW.
- If a section heading is useful context (e.g. "Required Qualifications"),
  keep it as a plain-text label.
- Preserve numeric requirements verbatim (e.g. "5+ years", "99.9% uptime").
"""

_CLEAN_JD_USER_TMPL = """\
Extract only the functional requirements and hard skills from the following
raw HTML job description.  Output plain text only.

RAW HTML:
{raw_html}
"""


# ── Injectable client protocol ────────────────────────────────────────────────


class _GenAIClientProtocol(Protocol):
    """Minimal protocol satisfied by google.genai.Client for type-checking.

    Keeping a Protocol (not importing the real Client) means this module
    stays importable even when google-genai is not installed in a test env.
    """

    def generate_content_text(self, *, model: str, system: str, prompt: str) -> str:
        """Generate content and return the plain-text response."""
        ...


class _RealGenAIClient:
    """Thin wrapper around google.genai.Client that satisfies _GenAIClientProtocol."""

    def __init__(self, api_key: str) -> None:
        """Initialise the underlying google.genai.Client.

        Args:
            api_key: Gemini API key for inference.
        """
        from google import genai
        from google.genai import types as _types

        self._client = genai.Client(api_key=api_key)
        self._types = _types

    def generate_content_text(self, *, model: str, system: str, prompt: str) -> str:
        """Call the Gemini API and return the plain-text response.

        Args:
            model: Gemini model ID (resolved from the registry, never hardcoded here).
            system: System instruction text.
            prompt: User-turn text to send to the model.

        Returns:
            Plain-text response string.

        Raises:
            ScraperError: if the model call fails or returns an empty response.
        """
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=system,
                ),
            )
        except Exception as exc:
            raise ScraperError(f"Model call failed: {exc}") from exc

        text = response.text
        if not text:
            raise ScraperError("Model returned an empty response for JD cleaning.")
        return text


def _get_default_client() -> _GenAIClientProtocol:
    """Return a real GenAI client using settings-resolved API key.

    Raises:
        ScraperError: if no API key is configured.
    """
    from config import get_settings

    settings = get_settings()
    api_key = settings.dev_gemini_key or settings.gemini_api_key
    if not api_key:
        raise ScraperError(
            "No Gemini API key configured. Set GEMINI_API_KEY or DEV_GEMINI_KEY in .env."
        )
    return _RealGenAIClient(api_key=api_key)


# ── Public functions ──────────────────────────────────────────────────────────


def fetch_raw_html(url: str) -> str:
    """Fetch the raw HTML content of a job description URL.

    Uses httpx with a fixed timeout; follows redirects up to 5 hops.

    Args:
        url: The public URL of the job description page.

    Returns:
        Raw HTML string (decoded from the response).

    Raises:
        ScraperError: if the URL cannot be fetched, returns a non-2xx status,
            or times out.
    """
    try:
        with httpx.Client(follow_redirects=True, timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = client.get(url)
    except httpx.TimeoutException as exc:
        raise ScraperError(f"Request timed out fetching {url!r}: {exc}") from exc
    except httpx.RequestError as exc:
        raise ScraperError(f"Network error fetching {url!r}: {exc}") from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise ScraperError(
            f"Non-2xx response fetching {url!r}: HTTP {response.status_code}"
        )

    return response.text


def clean_jd_html(
    raw_html: str,
    *,
    client: Any | None = None,
) -> str:
    """Use a BULK_CHEAP model to strip nav/sidebar/culture fluff from raw JD HTML.

    Returns only functional requirements and hard skills as plain text.
    Model output is treated as untrusted text; never rendered as HTML.

    The LLM client is injectable via the `client` parameter so unit tests can
    mock it without making real network calls.  When `client` is None the
    function constructs a real Gemini client from settings.

    Args:
        raw_html: Raw HTML fetched from the JD URL.
        client: Optional injectable client satisfying _GenAIClientProtocol.
            Defaults to a real google.genai.Client resolved from settings.

    Returns:
        Cleaned plain-text job description (functional requirements + hard skills).

    Raises:
        ScraperError: if model resolution fails or the model call fails.
    """
    registry = get_registry()
    model_or_upgrade = registry.get_model_id(Capability.BULK_CHEAP)

    # UpgradeRequired is a typed signal — propagate it as-is.
    from schema import UpgradeRequired

    if isinstance(model_or_upgrade, UpgradeRequired):
        # This should never happen in Free Mode (BULK_CHEAP always resolves),
        # but we propagate the signal rather than crash.
        raise ScraperError(
            f"BULK_CHEAP capability unavailable: {model_or_upgrade.reason}"
        )

    model_id: str = model_or_upgrade

    if client is None:
        client = _get_default_client()

    prompt = _CLEAN_JD_USER_TMPL.format(raw_html=raw_html)
    result: str = client.generate_content_text(
        model=model_id,
        system=_CLEAN_JD_SYSTEM_PROMPT,
        prompt=prompt,
    )
    if not result or not result.strip():
        raise ScraperError("Model returned an empty response for JD cleaning.")
    return result


def scrape_job_description(
    url: str,
    *,
    client: Any | None = None,
) -> str:
    """Convenience wrapper: fetch raw HTML then clean via BULK_CHEAP model.

    Args:
        url: Public URL of the job description.
        client: Optional injectable LLM client (for testing).

    Returns:
        Cleaned plain-text job description.

    Raises:
        ScraperError: if fetching or cleaning fails.
    """
    raw = fetch_raw_html(url)
    return clean_jd_html(raw, client=client)


# ── Exception ─────────────────────────────────────────────────────────────────


class ScraperError(Exception):
    """Raised when the scraper cannot fetch or parse a job description URL."""
