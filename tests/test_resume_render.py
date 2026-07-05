"""Tests for the structured résumé renderers (web/resume_render.py)."""

from __future__ import annotations

import io
import zipfile

from web.resume_builder import Contact, RoleBlock, StructuredResume
from web.resume_render import (
    structured_to_docx_bytes,
    structured_to_markdown,
    structured_to_pdf_bytes,
)

_RESUME = StructuredResume(
    contact=Contact(
        name="Sam Rivera", email="sam@example.com", phone="555-0100",
        location="NYC", links=["linkedin.com/in/sam"],
    ),
    summary="Systems engineer focused on latency and reliability.",
    skills=["Python", "Distributed systems", "Kubernetes"],
    experience=[
        RoleBlock(
            title="Staff Engineer", org="Acme", dates="2020 - 2023",
            bullets=["Cut p99 latency 40%", "Led billing rewrite"],
        )
    ],
    education=[RoleBlock(title="BSc Computer Science", org="MIT", dates="2016 - 2020")],
)


def test_markdown_is_a_real_resume_structure() -> None:
    md = structured_to_markdown(_RESUME)
    assert "# Sam Rivera" in md
    assert "sam@example.com" in md
    assert "## Summary" in md
    assert "## Skills" in md
    assert "## Experience" in md
    assert "### Staff Engineer — Acme" in md
    assert "- Cut p99 latency 40%" in md
    assert "## Education" in md
    assert "MIT" in md
    # The internal reasoning must NOT appear in the document.
    assert "why it fits" not in md.lower()
    assert "relevance" not in md.lower()


def test_pdf_bytes_are_a_pdf() -> None:
    data = structured_to_pdf_bytes(_RESUME)
    assert data[:5] == b"%PDF-"
    assert len(data) > 500


def test_docx_is_valid_and_has_content() -> None:
    data = structured_to_docx_bytes(_RESUME)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "word/document.xml" in zf.namelist()
        body = zf.read("word/document.xml").decode("utf-8")
    assert "Sam Rivera" in body
    assert "Staff Engineer" in body
    assert "Cut p99 latency 40%" in body


def test_empty_resume_renders_without_error() -> None:
    empty = StructuredResume(Contact(), "", [], [], [])
    assert structured_to_pdf_bytes(empty)[:5] == b"%PDF-"
    with zipfile.ZipFile(io.BytesIO(structured_to_docx_bytes(empty))) as zf:
        assert "word/document.xml" in zf.namelist()


def test_pdf_escapes_hostile_text() -> None:
    hostile = StructuredResume(
        Contact(name="<script>alert(1)</script>"), "", [], [], []
    )
    assert structured_to_pdf_bytes(hostile)[:5] == b"%PDF-"  # renders inert, no raise
