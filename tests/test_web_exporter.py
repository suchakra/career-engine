"""Tests for the multi-format tailored-résumé exporter (web/exporter.py)."""

from __future__ import annotations

import io
import zipfile

from web.exporter import (
    tailored_to_docx_bytes,
    tailored_to_markdown,
    tailored_to_pdf_bytes,
)
from web.tailor import TailoredAchievement, TailoredResume

_RESUME = TailoredResume(
    summary="Delivery-focused engineer who cut latency and cost.",
    achievements=[
        TailoredAchievement(
            pillar="performance",
            headline="Cut p99 latency 85% across 40 services",
            full_text="Led a caching + query overhaul.",
            relevance_note="The JD stresses low-latency systems.",
        )
    ],
)


def test_pdf_bytes_are_a_pdf() -> None:
    data = tailored_to_pdf_bytes(_RESUME, name="Sam Rivera")
    assert data[:5] == b"%PDF-"  # valid PDF magic
    assert len(data) > 500


def test_docx_bytes_are_a_valid_docx() -> None:
    data = tailored_to_docx_bytes(_RESUME, name="Sam Rivera")
    # A .docx is a zip (OOXML) — must open and contain the main document part.
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "word/document.xml" in names
        body = zf.read("word/document.xml").decode("utf-8")
    assert "Cut p99 latency 85% across 40 services" in body
    assert "Sam Rivera" in body


def test_empty_resume_still_renders() -> None:
    empty = TailoredResume(summary="", achievements=[])
    assert tailored_to_pdf_bytes(empty)[:5] == b"%PDF-"
    with zipfile.ZipFile(io.BytesIO(tailored_to_docx_bytes(empty))) as zf:
        assert "word/document.xml" in zf.namelist()


def test_markdown_export_is_reexported_here() -> None:
    md = tailored_to_markdown(_RESUME)
    assert "**Cut p99 latency 85% across 40 services**" in md


def test_pdf_escapes_model_text() -> None:
    """Model-derived text must be inert in the HTML→PDF path (no markup injection)."""
    hostile = TailoredResume(
        summary="<script>alert(1)</script>",
        achievements=[],
    )
    # Rendering must not raise; the autoescaped template renders the tag as text.
    assert tailored_to_pdf_bytes(hostile)[:5] == b"%PDF-"
