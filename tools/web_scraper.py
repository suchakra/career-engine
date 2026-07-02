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

import ipaddress
import socket
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from models.registry import get_registry
from schema import Capability

# ── Constants ─────────────────────────────────────────────────────────────────

_FETCH_TIMEOUT_SECONDS: float = 20.0
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_MAX_REDIRECTS: int = 5
# Hostnames that resolve to (or alias) the cloud metadata service — blocked even
# before DNS resolution as a belt-and-braces guard.
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({"metadata", "metadata.google.internal"})

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


def _resolve_addresses(host: str) -> list[str]:
    """Resolve a hostname to its IP address strings (injectable for tests)."""
    infos = socket.getaddrinfo(host, None)
    return [str(info[4][0]) for info in infos]


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if an IP is private/loopback/link-local/reserved (SSRF target)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → treat as unsafe
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _assert_safe_url(url: str, *, resolver: Callable[[str], list[str]]) -> None:
    """Reject non-HTTP(S) URLs and any host resolving to a non-public address.

    Guards against SSRF: the JD URL is fully user-controlled, and the fetched
    body is returned to the caller. Without this, a user could point the scraper
    at the cloud metadata service or an internal VPC endpoint and exfiltrate the
    response (ARCHITECTURE §5 — the runtime SA can read Secret Manager).

    Raises:
        ScraperError: if the scheme is not http/https or the host resolves to a
            private, loopback, link-local, reserved, or metadata address.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ScraperError(
            f"Refusing to fetch non-HTTP(S) URL scheme {scheme or '(none)'!r}: {url!r}"
        )
    host = parsed.hostname
    if not host:
        raise ScraperError(f"URL has no host: {url!r}")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise ScraperError("Refusing to fetch the cloud metadata endpoint.")
    try:
        addresses = resolver(host)
    except OSError as exc:
        raise ScraperError(f"Network error resolving {host!r}: {exc}") from exc
    if not addresses:
        raise ScraperError(f"Could not resolve host {host!r}.")
    for addr in addresses:
        if _is_blocked_ip(addr):
            raise ScraperError(
                "Refusing to fetch a URL that resolves to a private, loopback, or "
                f"link-local address ({addr}). Only public job-posting URLs are allowed."
            )


def fetch_raw_html(
    url: str,
    *,
    resolver: Callable[[str], list[str]] = _resolve_addresses,
) -> str:
    """Fetch the raw HTML content of a *public* job description URL.

    SSRF-hardened: the scheme must be http/https and the host (revalidated on
    every redirect hop) must resolve to a public address; redirects are followed
    manually up to :data:`_MAX_REDIRECTS` so an internal-address redirect cannot
    slip past the check.

    Args:
        url: The public URL of the job description page.
        resolver: Hostname→IP resolver (injectable for tests).

    Returns:
        Raw HTML string (decoded from the response).

    Raises:
        ScraperError: if the URL is unsafe (non-HTTP(S) / private address), can
            not be fetched, returns a non-2xx status, times out, or redirects too
            many times.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        _assert_safe_url(current, resolver=resolver)
        try:
            with httpx.Client(follow_redirects=False, timeout=_FETCH_TIMEOUT_SECONDS) as client:
                response = client.get(current)
        except httpx.TimeoutException as exc:
            raise ScraperError(f"Request timed out fetching {current!r}: {exc}") from exc
        except httpx.RequestError as exc:
            raise ScraperError(f"Network error fetching {current!r}: {exc}") from exc

        if 300 <= response.status_code < 400:
            location = response.headers.get("location")
            if not location:
                raise ScraperError(f"Redirect without a Location header from {current!r}.")
            current = urljoin(current, location)
            continue
        if response.status_code < 200 or response.status_code >= 300:
            raise ScraperError(
                f"Non-2xx response fetching {current!r}: HTTP {response.status_code}"
            )
        return response.text

    raise ScraperError(f"Too many redirects (> {_MAX_REDIRECTS}) fetching {url!r}.")


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
