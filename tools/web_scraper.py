"""Two-step job-description scraper — typed stub.

Phase 0 — interface only.  Phase 1 (WS-B) implements the bodies.

Step 1: fetch(url) → raw HTML string.
Step 2: clean(html) → uses a BULK_CHEAP model (via registry) to strip
    navigation, sidebars, and culture/mission fluff, leaving only
    functional requirements and hard skills.

Design rules:
- The scraper requests BULK_CHEAP capability via the registry; it never
  names a model directly.
- Model output is treated as untrusted text; it is NOT rendered as HTML.
- Returns a plain string suitable for further processing.
"""

from __future__ import annotations

from models.registry import get_registry
from schema import Capability


def fetch_raw_html(url: str) -> str:
    """Fetch the raw HTML content of a job description URL.

    Args:
        url: The public URL of the job description page.

    Returns:
        Raw HTML string.

    Raises:
        ScraperError: if the URL cannot be fetched or returns a non-2xx status.
    """
    raise NotImplementedError("web_scraper.fetch_raw_html is a Phase 1 task.")


def clean_jd_html(raw_html: str) -> str:
    """Use a BULK_CHEAP model to strip nav/sidebar/culture fluff from raw JD HTML.

    Returns only functional requirements and hard skills as plain text.
    Model output is treated as untrusted text; never rendered as HTML.

    Args:
        raw_html: Raw HTML fetched from the JD URL.

    Returns:
        Cleaned plain-text job description.

    Raises:
        ScraperError: if model resolution or the model call fails.
        UpgradeRequired: if BULK_CHEAP capability is unavailable (should not
            happen in Free Mode, but propagated for safety).
    """
    registry = get_registry()
    _model_or_upgrade = registry.get_model_id(Capability.BULK_CHEAP)
    raise NotImplementedError("web_scraper.clean_jd_html is a Phase 1 task.")


def scrape_job_description(url: str) -> str:
    """Convenience wrapper: fetch + clean in one call.

    Args:
        url: Public URL of the job description.

    Returns:
        Cleaned plain-text job description.
    """
    raw = fetch_raw_html(url)
    return clean_jd_html(raw)


class ScraperError(Exception):
    """Raised when the scraper cannot fetch or parse a job description URL."""
