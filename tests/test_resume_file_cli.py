"""Tests for resume-file CLI ingestion wiring (Phase 1.7-A).

Exercises the boundary glue — MIME detection + reading bytes + routing to the
vision parser — with a mocked multimodal client (no network).  Full
interactive-session wiring is covered indirectly by the existing suite; here we
pin the new helper behavior and the failure paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from cli.app import guess_resume_mime, parse_resume_file
from integration.model_client import GeminiModelClient
from tests.test_resume_parser import _TWO_ROLE_RESUME, MockMultimodalClient
from tools.resume_parser import ParseError


def _client() -> GeminiModelClient:
    """A mocked multimodal client typed as GeminiModelClient for the call site."""
    return cast(GeminiModelClient, MockMultimodalClient(_TWO_ROLE_RESUME))


class TestGuessResumeMime:
    """Extension → MIME mapping for resume files."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("cv.pdf", "application/pdf"),
            ("cv.PDF", "application/pdf"),
            ("scan.png", "image/png"),
            ("photo.jpg", "image/jpeg"),
            ("photo.jpeg", "image/jpeg"),
            ("shot.webp", "image/webp"),
        ],
    )
    def test_known_extensions(self, name: str, expected: str) -> None:
        """Known resume extensions map to their MIME type."""
        assert guess_resume_mime(Path(name)) == expected


class TestParseResumeFile:
    """parse_resume_file reads bytes and routes them through the parser."""

    def test_pdf_file_seeds_entries(self, tmp_path: Path) -> None:
        """A .pdf file is read and parsed into a non-empty timeline."""
        f = tmp_path / "resume.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        entries = parse_resume_file(f, client=cast(GeminiModelClient, client))
        assert len(entries) == 2
        # routed with the correct MIME + the raw bytes
        assert client.calls[0]["media"][0].mime_type == "application/pdf"
        assert client.calls[0]["media"][0].data == b"%PDF-1.4 fake"

    @pytest.mark.parametrize(
        ("name", "mime"),
        [("r.png", "image/png"), ("r.jpg", "image/jpeg"), ("r.webp", "image/webp")],
    )
    def test_image_files_route_through_parser(
        self, tmp_path: Path, name: str, mime: str
    ) -> None:
        """Image resumes route through the same multimodal parse path."""
        f = tmp_path / name
        f.write_bytes(b"BINARY-IMAGE")
        client = MockMultimodalClient(_TWO_ROLE_RESUME)
        entries = parse_resume_file(f, client=cast(GeminiModelClient, client))
        assert len(entries) == 2
        assert client.calls[0]["media"][0].mime_type == mime

    def test_unsupported_extension_raises_parse_error(self, tmp_path: Path) -> None:
        """A .docx file is rejected with ParseError (caller surfaces it safely)."""
        f = tmp_path / "resume.docx"
        f.write_bytes(b"PK\x03\x04 docx")
        with pytest.raises(ParseError):
            parse_resume_file(f, client=_client())

    def test_empty_file_raises_parse_error(self, tmp_path: Path) -> None:
        """An empty file raises ParseError rather than crashing."""
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        with pytest.raises(ParseError):
            parse_resume_file(f, client=_client())
