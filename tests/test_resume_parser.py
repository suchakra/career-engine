"""Tests for the vision resume parser (Phase 1.5 / 1.5-INGEST).

The multimodal model client is mocked — no network calls — and fixtures are
deterministic structured JSON.  Covers: structured parse, PDF + image routing
through the multimodal path, coverage_through derivation in ingest_node, the
early-career entry types, ParseError handling, and the no-PII / no-hardcoded
-model contract.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from integration.model_client import MediaPart
from schema import (
    CareerEngineState,
    EntryStatus,
    ExperienceType,
    PhaseStatus,
)
from tools.resume_parser import ParseError, parse_resume

PNG_BYTES = b"\x89PNG\r\n\x1a\nFAKE-IMAGE-DATA"
PDF_BYTES = b"%PDF-1.4 FAKE-PDF-DATA"


class MockMultimodalClient:
    """Records multimodal calls and returns a scripted response (no network)."""

    def __init__(self, response: str) -> None:
        """Initialise with the canned model response."""
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def generate_multimodal(
        self,
        *,
        model_id: str,
        system: str,
        prompt: str,
        media: Sequence[MediaPart],
    ) -> str:
        """Record the call and return the scripted response."""
        self.calls.append(
            {
                "model_id": model_id,
                "system": system,
                "prompt": prompt,
                "media": list(media),
            }
        )
        return self._response


def _timeline_json(entries: list[dict[str, Any]]) -> str:
    """Build a model-style timeline JSON response."""
    return json.dumps({"timeline": entries, "summary": "A candidate."})


_TWO_ROLE_RESUME = _timeline_json(
    [
        {
            "type": "full_time",
            "title": "Senior Engineer",
            "org": "Acme",
            "start_date": "2022",
            "end_date": "",
            "bullets": ["Led the platform team"],
        },
        {
            "type": "full_time",
            "title": "Engineer",
            "org": "Globex",
            "start_date": "2019",
            "end_date": "2022",
            "bullets": ["Built the billing service"],
        },
    ]
)

_EARLY_CAREER_RESUME = _timeline_json(
    [
        {
            "type": "education",
            "title": "B.S. Computer Science",
            "org": "State University",
            "start_date": "2020",
            "end_date": "2024",
            "bullets": [],
        },
        {
            "type": "internship",
            "title": "SWE Intern",
            "org": "Acme",
            "start_date": "2023",
            "end_date": "2023",
            "bullets": ["Shipped a feature"],
        },
        {
            "type": "project",
            "title": "Capstone App",
            "org": "University",
            "start_date": "2023",
            "end_date": "2024",
            "bullets": ["Built a mobile app"],
        },
        {
            "type": "project",
            "title": "Open-source CLI",
            "org": "GitHub",
            "start_date": "2022",
            "end_date": "2023",
            "bullets": ["Maintained a CLI tool"],
        },
    ]
)


# ── Structured parse ──────────────────────────────────────────────────────────


class TestParseResumeStructured:
    """parse_resume returns validated Entries from a structured model response."""

    def test_parses_two_roles_with_types_and_dates(self) -> None:
        """A two-role resume yields >=2 Entries with correct type/dates."""
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        entries = parse_resume(PDF_BYTES, "application/pdf", client=client)

        assert len(entries) == 2
        assert entries[0].title == "Senior Engineer"
        assert entries[0].type == ExperienceType.FULL_TIME
        assert entries[0].end_date == ""  # 'present' handled
        assert entries[1].start_date == "2019"
        assert entries[1].end_date == "2022"
        # All entries are sourced from the resume
        assert all(e.source == "resume" for e in entries)

    def test_layout_aware_prompt_used(self) -> None:
        """The system prompt instructs the model to read multi-column layout."""
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        parse_resume(PDF_BYTES, "application/pdf", client=client)
        system = client.calls[0]["system"]
        assert "multi-column" in system.lower() or "layout" in system.lower()

    def test_documented_vs_needs_quantifying_status(self) -> None:
        """Entries with bullets are documented; bullet-less ones need quantifying."""
        client = MockMultimodalClient(_EARLY_CAREER_RESUME)
        entries = parse_resume(PNG_BYTES, "image/png", client=client)
        by_title = {e.title: e for e in entries}
        # Education entry has no bullets → needs_quantifying
        assert by_title["B.S. Computer Science"].status == EntryStatus.NEEDS_QUANTIFYING
        # Internship has a bullet → documented
        assert by_title["SWE Intern"].status == EntryStatus.DOCUMENTED


# ── PDF + image both route through the multimodal path ────────────────────────


class TestMultimodalRouting:
    """Both PDF and image inputs carry binary + prompt into the multimodal call."""

    @pytest.mark.parametrize(
        ("data", "mime"),
        [(PDF_BYTES, "application/pdf"), (PNG_BYTES, "image/png")],
    )
    def test_media_includes_binary_and_prompt(self, data: bytes, mime: str) -> None:
        """The mock records a MediaPart with the raw bytes + a non-empty prompt."""
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        parse_resume(data, mime, client=client)

        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["prompt"]  # non-empty text instruction
        media = call["media"]
        assert len(media) == 1
        assert isinstance(media[0], MediaPart)
        assert media[0].data == data
        assert media[0].mime_type == mime

    def test_jpg_mime_accepted(self) -> None:
        """A jpeg image is accepted and routed."""
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        entries = parse_resume(b"\xff\xd8\xff JPEG", "image/jpeg", client=client)
        assert len(entries) == 2


# ── Early-career resume ───────────────────────────────────────────────────────


class TestEarlyCareer:
    """An education-heavy resume yields education/internship/project entries."""

    def test_early_career_entry_types(self) -> None:
        """Education + internship + 2 projects yield entries of those types."""
        client = MockMultimodalClient(_EARLY_CAREER_RESUME)
        entries = parse_resume(PDF_BYTES, "application/pdf", client=client)

        types = [e.type for e in entries]
        assert ExperienceType.EDUCATION in types
        assert ExperienceType.INTERNSHIP in types
        assert types.count(ExperienceType.PROJECT) == 2


# ── coverage_through derivation (ingest_node, vision-preseeded path) ──────────


class TestCoverageThrough:
    """ingest_node derives coverage_through from the latest end_date."""

    def test_coverage_through_set_from_latest_end_date(self) -> None:
        """A timeline whose latest closed role ends 2022 sets coverage_through=2022."""
        from workflows.nodes import ingest_node

        client = MockMultimodalClient(
            _timeline_json(
                [
                    {
                        "type": "full_time",
                        "title": "Engineer",
                        "org": "Globex",
                        "start_date": "2019",
                        "end_date": "2022",
                        "bullets": [],
                    }
                ]
            )
        )
        entries = parse_resume(PDF_BYTES, "application/pdf", client=client)
        state = CareerEngineState(work_timeline=entries, reference_date="2026-06-29")
        result = ingest_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert result.coverage_through == "2022"

    def test_present_role_yields_empty_coverage(self) -> None:
        """A 'present' (open) role makes coverage_through empty (freshest boundary)."""
        from workflows.nodes import ingest_node

        client = MockMultimodalClient(_TWO_ROLE_RESUME)  # first role end_date=""
        entries = parse_resume(PDF_BYTES, "application/pdf", client=client)
        state = CareerEngineState(work_timeline=entries, reference_date="2026-06-29")
        result = ingest_node(state)

        assert result.coverage_through == ""


# ── Error paths + privacy + contract ──────────────────────────────────────────


class TestParseErrors:
    """parse_resume raises ParseError on bad input/output and never stores bytes."""

    def test_empty_bytes_raises(self) -> None:
        """Empty file bytes raise ParseError before any model call."""
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        with pytest.raises(ParseError):
            parse_resume(b"", "application/pdf", client=client)
        assert client.calls == []  # no model call on empty input

    def test_unsupported_mime_raises(self) -> None:
        """A DOCX MIME type is rejected with guidance."""
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        with pytest.raises(ParseError, match="Unsupported"):
            parse_resume(
                b"PK\x03\x04",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                client=client,
            )

    def test_garbage_model_output_raises(self) -> None:
        """Non-JSON / empty model output raises ParseError."""
        client = MockMultimodalClient("I could not read this document, sorry.")
        with pytest.raises(ParseError):
            parse_resume(PDF_BYTES, "application/pdf", client=client)

    def test_empty_timeline_raises(self) -> None:
        """A valid-JSON but empty timeline raises ParseError."""
        client = MockMultimodalClient(json.dumps({"timeline": [], "summary": "x"}))
        with pytest.raises(ParseError):
            parse_resume(PDF_BYTES, "application/pdf", client=client)

    def test_raw_bytes_never_stored_on_state(self) -> None:
        """The raw document bytes never appear in any Entry or serialized state."""
        from workflows.nodes import ingest_node

        marker = b"SECRET-RESUME-PII-MARKER"
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        entries = parse_resume(PDF_BYTES + marker, "application/pdf", client=client)
        state = CareerEngineState(work_timeline=entries, reference_date="2026-06-29")
        result = ingest_node(state)

        dumped = result.model_dump_json()
        assert "SECRET-RESUME-PII-MARKER" not in dumped


class TestNoHardcodedModelNames:
    """No hardcoded 'gemini-' model names in the parser or the adapter."""

    def test_no_gemini_literal_in_source(self) -> None:
        """tools/resume_parser.py and the adapter request capabilities, not models."""
        root = Path(__file__).resolve().parent.parent
        for rel in ("tools/resume_parser.py", "integration/model_client.py"):
            text = (root / rel).read_text(encoding="utf-8")
            assert "gemini-" not in text, f"hardcoded model name in {rel}"
