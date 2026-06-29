"""Vision-first resume ingestion (Phase 1.5 / contract v2.0.0).

Parses an uploaded resume — a PDF, a scanned page, or a photo of a printed
resume — into a structured :class:`~schema.Entry` timeline by sending the
document directly to a natively-multimodal Gemini model (``SPEED_FAST`` →
resolved via the registry, never hardcoded).

Why vision, not ``pdf → text`` (ARCHITECTURE.md §12.2):
    A multimodal model reads LAYOUT — multi-column designs, table/grid hacks,
    even a photo of a printed page — where ``pdf → text`` extraction flattens
    columns and drops tables.  Gemini also understands PDFs natively, so we send
    PDF bytes inline without a local rasterization/OCR pipeline (no extra dep).

Privacy:
    The uploaded bytes are PII.  This module never persists them — it returns
    only the structured ``list[Entry]`` and discards the bytes when it returns.
    The bytes are never written to ``CareerEngineState``.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from integration.model_client import MediaPart
from models.registry import get_registry
from schema import Capability, Entry, EntryStatus, ExperienceType, UpgradeRequired
from workflows.prompts import RESUME_PARSE_SYSTEM_PROMPT

# ── Accepted input formats ────────────────────────────────────────────────────
# Gemini handles PDF natively (document understanding) and standard raster
# images.  DOCX has no native image and is out of scope (convert-to-PDF first).

_SUPPORTED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
    }
)

_PARSE_INSTRUCTION: str = (
    "Read this resume document and extract every experience entry as structured "
    "JSON per the schema in your instructions.  Capture jobs, internships, "
    "projects, research, open-source, leadership, and education."
)


class ParseError(Exception):
    """Raised when a resume cannot be parsed into a non-empty timeline."""


class _MultimodalClient(Protocol):
    """Minimal protocol satisfied by ``integration.model_client.GeminiModelClient``."""

    def generate_multimodal(
        self,
        *,
        model_id: str,
        system: str,
        prompt: str,
        media: Any,
    ) -> str:
        """Generate text from a prompt plus binary media parts."""
        ...


def _parse_json_object(text: str) -> dict[str, Any]:
    """Extract and parse a JSON object from a model response string.

    Handles markdown fences and bare objects; returns an empty dict on failure.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not obj_match:
        return {}
    try:
        parsed: object = json.loads(obj_match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_default_client() -> _MultimodalClient:
    """Construct the real multimodal client using the settings-resolved key."""
    from config import get_settings
    from integration.model_client import GeminiModelClient

    settings = get_settings()
    api_key = settings.gemini_api_key or settings.dev_gemini_key or None
    return GeminiModelClient(api_key=api_key)


def _resolve_speed_fast_model() -> str:
    """Resolve the SPEED_FAST (multimodal Flash) model ID via the registry.

    Raises:
        ParseError: if the registry cannot resolve a SPEED_FAST model.
    """
    from config import get_settings

    registry = get_registry()
    settings = get_settings()
    model_or_upgrade = registry.get_model_id(
        Capability.SPEED_FAST, access_mode=settings.access_mode
    )
    if isinstance(model_or_upgrade, UpgradeRequired):
        raise ParseError(
            "No SPEED_FAST model available to parse the resume "
            f"({model_or_upgrade.reason})."
        )
    return model_or_upgrade


def _entry_from_item(item: dict[str, Any]) -> Entry:
    """Build an Entry from one parsed timeline item.

    An entry with existing bullets is ``documented`` (ingest then decides whether
    it is already metric-bearing); an entry with no bullets ``needs_quantifying``.
    """
    try:
        exp_type = ExperienceType(item.get("type", "other"))
    except ValueError:
        exp_type = ExperienceType.OTHER

    bullets = [str(b) for b in item.get("bullets", []) if str(b).strip()]
    status = EntryStatus.DOCUMENTED if bullets else EntryStatus.NEEDS_QUANTIFYING

    return Entry(
        type=exp_type,
        title=str(item.get("title", "Untitled")),
        org=str(item.get("org", "")),
        start_date=str(item.get("start_date", "")),
        end_date=str(item.get("end_date", "")),
        source="resume",
        bullets=bullets,
        status=status,
    )


def parse_resume(
    file_bytes: bytes,
    mime_type: str,
    *,
    client: _MultimodalClient | None = None,
) -> list[Entry]:
    """Parse a resume document into a structured timeline of experience entries.

    Sends the document directly to a multimodal Gemini model (PDF and images
    supported natively) and validates the structured response into Entries.

    Args:
        file_bytes: Raw bytes of the resume (PDF or image).  Treated as PII —
            never persisted; discarded when this function returns.
        mime_type: The document MIME type (e.g. ``application/pdf``,
            ``image/png``).
        client: Optional injected multimodal client (mocked in tests).  When
            ``None``, a real ``GeminiModelClient`` is built from settings.

    Returns:
        A list of ``Entry`` objects (``source="resume"``), newest-first as
        returned by the model.

    Raises:
        ParseError: if ``file_bytes`` is empty, the MIME type is unsupported,
            no model is available, or the model returns nothing parseable.
    """
    if not file_bytes:
        raise ParseError("Empty resume file: no bytes to parse.")

    normalized_mime = mime_type.strip().lower()
    if normalized_mime not in _SUPPORTED_MIME_TYPES:
        raise ParseError(
            f"Unsupported resume MIME type {mime_type!r}.  "
            f"Supported: {', '.join(sorted(_SUPPORTED_MIME_TYPES))}.  "
            "Convert DOCX to PDF first."
        )

    model_id = _resolve_speed_fast_model()
    active_client = client if client is not None else _build_default_client()

    response_text = active_client.generate_multimodal(
        model_id=model_id,
        system=RESUME_PARSE_SYSTEM_PROMPT,
        prompt=_PARSE_INSTRUCTION,
        media=[MediaPart(data=file_bytes, mime_type=normalized_mime)],
    )

    parsed = _parse_json_object(response_text)
    items = parsed.get("timeline", [])
    if not isinstance(items, list) or not items:
        raise ParseError(
            "Could not extract any experience entries from the resume "
            "(empty or unparseable model output)."
        )

    entries = [_entry_from_item(item) for item in items if isinstance(item, dict)]
    if not entries:
        raise ParseError("Resume produced no valid experience entries.")
    return entries
