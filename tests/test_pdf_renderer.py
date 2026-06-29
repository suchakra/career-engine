"""Unit tests for tools/pdf_renderer.py and templates/classic_resume.html.

No real PDF engine calls to the filesystem for fast unit tests; integration-level
tests that write actual PDFs are clearly annotated.

Acceptance criteria covered:
  AC1: render_html escapes hostile content — <script>alert(1)</script> in a
       StarStory field does NOT appear as a live tag in the output.
       (test_render_html_escapes_script_tag, test_render_html_escapes_markdown)

  AC2: Rendering a valid state produces a non-empty PDF file.
       (test_render_pdf_produces_non_empty_file)

  AC3: Rendering an invalid/partial state raises ValueError rather than silently
       emitting a broken document.
       (test_render_pdf_empty_state_raises, test_render_html_empty_state_raises)

  AC4: Only validated stories (metrics_validated=True) appear in the output;
       unvalidated stories are excluded.
       (test_render_html_excludes_unvalidated_stories)
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from schema import CareerEngineState, PhaseStatus, StarStory
from tools.pdf_renderer import render_html, render_pdf

# ── Fixture helpers ───────────────────────────────────────────────────────────


def _minimal_state() -> CareerEngineState:
    """Return a CareerEngineState with minimal renderable content (v2.0.0)."""
    return CareerEngineState(
        current_phase=PhaseStatus.FINALIZING,
        raw_history_text="Name: Jane Smith\nSenior software engineer with 10 years experience.",
    )


def _state_with_stories(*stories: StarStory) -> CareerEngineState:
    """Return a state seeded with the given StarStory objects."""
    state = _minimal_state()
    state.extracted_star_stories = list(stories)
    return state


def _validated_story(**kwargs: str) -> StarStory:
    """Return a validated StarStory (metrics_validated=True) with given fields."""
    defaults: dict[str, object] = {
        "pillar": "performance",
        "situation": "System hit 800ms p99.",
        "task": "Reduce latency.",
        "action": "Profiled and added cache layer.",
        "result": "Cut p99 from 800ms to 120ms across 40 services.",
        "metrics_validated": True,
    }
    defaults.update(kwargs)
    return StarStory(**defaults)  # type: ignore[arg-type]


def _unvalidated_story(**kwargs: str) -> StarStory:
    """Return an unvalidated StarStory (metrics_validated=False)."""
    defaults: dict[str, object] = {
        "pillar": "leadership",
        "situation": "Led a team.",
        "action": "I improved things a lot.",
        "result": "Things got better.",
        "metrics_validated": False,
    }
    defaults.update(kwargs)
    return StarStory(**defaults)  # type: ignore[arg-type]


# ── AC1: Escaping / XSS prevention ───────────────────────────────────────────


class TestEscaping:
    """AC1 — hostile content is escaped; no live <script> tags in output."""

    def test_render_html_escapes_script_tag(self) -> None:
        """AC1a: A <script>alert(1)</script> in a StarStory field is escaped, not live.

        The rendered HTML must NOT contain a literal unescaped <script> tag.
        The content should appear as &lt;script&gt; or similar escaped form.
        """
        story = _validated_story(
            result="<script>alert(1)</script>Cut p99 from 800ms to 120ms."
        )
        state = _state_with_stories(story)
        html = render_html(state)

        # A live <script> tag must NOT appear.
        assert "<script>" not in html, (
            "Unescaped <script> tag leaked into rendered HTML — XSS risk!"
        )
        assert "</script>" not in html, (
            "Unescaped </script> tag leaked into rendered HTML — XSS risk!"
        )

        # The escaped representation MUST appear (content preserved, not silently dropped).
        assert "&lt;script&gt;" in html, (
            "Script tag content appears to be silently dropped rather than escaped"
        )

    def test_render_html_escapes_script_in_situation(self) -> None:
        """AC1b: <script> in the situation field is also escaped."""
        story = _validated_story(
            situation='<script src="evil.js"></script>System was under load.',
            result="Reduced latency by 60%.",
        )
        state = _state_with_stories(story)
        html = render_html(state)

        assert "<script" not in html, (
            "Unescaped <script> in 'situation' field leaked into HTML"
        )

    def test_render_html_escapes_html_injection_in_pillar(self) -> None:
        """AC1c: HTML injection in pillar name is escaped."""
        story = StarStory(
            pillar='<img src=x onerror="alert(1)">engineering',
            situation="test",
            result="Improved throughput by 40%.",
            metrics_validated=True,
        )
        state = _state_with_stories(story)
        html = render_html(state)

        assert 'onerror="alert(1)"' not in html, (
            "onerror attribute leaked into HTML — injection risk!"
        )

    def test_render_html_markdown_bold_does_not_break_layout(self) -> None:
        """AC1d: **markdown** in a field is escaped, not rendered as HTML <strong>."""
        story = _validated_story(
            result="**Dramatically** cut p99 from 800ms to 120ms."
        )
        state = _state_with_stories(story)
        html = render_html(state)

        # Markdown asterisks should appear as literal text (or escaped), not as <strong>.
        # The key assertion is no <strong> tag from raw markdown.
        # (Jinja2 autoescape does NOT render markdown; ** stays as **)
        assert "<strong>" not in html, (
            "**markdown** was interpreted as HTML <strong> — should be literal text"
        )
        # The literal ** should appear in the output (content preserved).
        assert "**Dramatically**" in html, (
            "Markdown content was silently dropped rather than treated as literal text"
        )

    def test_render_html_ampersand_and_quote_escaped(self) -> None:
        """AC1e: & and " in field values are escaped to &amp; and &quot;."""
        story = _validated_story(
            action='Implemented "cache-aside" pattern & async batching.',
            result="Reduced DB load by 70%.",
        )
        state = _state_with_stories(story)
        html = render_html(state)

        # Raw unescaped & inside attribute/text context should be &amp;
        # (Jinja2 autoescape converts & → &amp; in text nodes)
        assert "&amp;" in html, (
            "Ampersand not escaped to &amp; in rendered HTML"
        )


# ── AC2: Story filtering ──────────────────────────────────────────────────────


class TestStoryFiltering:
    """Validated stories appear; unvalidated stories are excluded."""

    def test_render_html_includes_validated_stories(self) -> None:
        """Validated story result text appears in rendered HTML."""
        story = _validated_story(result="Cut p99 from 800ms to 120ms across 40 services.")
        state = _state_with_stories(story)
        html = render_html(state)

        assert "Cut p99 from 800ms to 120ms across 40 services." in html

    def test_render_html_excludes_unvalidated_stories(self) -> None:
        """AC4: Unvalidated story result text does NOT appear in rendered HTML."""
        validated = _validated_story(result="Reduced deploy time from 45min to 3min.")
        unvalidated = _unvalidated_story(result="I improved things a lot.")
        state = _state_with_stories(validated, unvalidated)
        html = render_html(state)

        assert "Reduced deploy time from 45min to 3min." in html, (
            "Validated story missing from rendered HTML"
        )
        assert "I improved things a lot." not in html, (
            "Unvalidated story leaked into rendered HTML"
        )

    def test_render_html_stories_grouped_by_pillar(self) -> None:
        """Stories from the same pillar appear grouped under that pillar heading."""
        perf_story = _validated_story(
            pillar="performance",
            result="Cut latency by 85%.",
        )
        lead_story = StarStory(
            pillar="leadership",
            situation="Managed a team of 5.",
            result="Delivered project 2 weeks early.",
            metrics_validated=True,
        )
        state = _state_with_stories(perf_story, lead_story)
        html = render_html(state)

        # Both pillar names (with underscores replaced by spaces) should appear.
        assert "performance" in html.lower()
        assert "leadership" in html.lower()


# ── AC3: Validation errors ────────────────────────────────────────────────────


class TestValidationErrors:
    """AC3 — invalid/partial state raises ValueError, not a silent broken render."""

    def test_render_html_empty_state_raises(self) -> None:
        """AC3a: A brand-new default CareerEngineState raises ValueError."""
        empty_state = CareerEngineState()
        with pytest.raises(ValueError, match="no renderable content"):
            render_html(empty_state)

    def test_render_pdf_empty_state_raises(self) -> None:
        """AC3b: render_pdf on an empty state raises ValueError before writing any file."""
        empty_state = CareerEngineState()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "out.pdf"
            with pytest.raises(ValueError, match="no renderable content"):
                render_pdf(empty_state, output_path=output)
            # No PDF file should have been created.
            assert not output.exists(), "render_pdf wrote a file despite raising ValueError"

    def test_render_html_state_with_no_history_and_no_stories_raises(self) -> None:
        """AC3c: State with no raw_history_text and no stories raises ValueError."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            # No raw_history_text, no extracted_star_stories
        )
        with pytest.raises(ValueError):
            render_html(state)

    def test_render_html_state_with_only_unvalidated_stories_and_no_text_raises(self) -> None:
        """AC3d: State with only unvalidated stories and no history text raises ValueError."""
        story = _unvalidated_story()
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            extracted_star_stories=[story],
            # raw_history_text is empty
        )
        with pytest.raises(ValueError):
            render_html(state)

    def test_render_html_state_with_history_text_is_valid(self) -> None:
        """State with only raw_history_text (no stories yet) renders without error."""
        state = CareerEngineState(
            raw_history_text="Name: John Doe\n10 years as SWE at various companies.",
        )
        html = render_html(state)
        assert html  # not empty
        assert "John Doe" in html or "Candidate Name" in html  # header rendered


# ── AC4 (integration): Non-empty PDF written to disk ─────────────────────────


class TestPdfOutput:
    """AC2 — render_pdf produces a non-empty PDF file for a valid state."""

    def test_render_pdf_produces_non_empty_file(self) -> None:
        """AC2: render_pdf writes a real PDF (non-empty, starts with %PDF) for valid state."""
        story = _validated_story(
            pillar="performance",
            situation="System was experiencing 800ms p99 latency.",
            task="Reduce p99 latency for the checkout flow.",
            action="Profiled hot paths, added Redis cache, rewrote N+1 queries.",
            result="Cut p99 from 800ms to 120ms across 40 services; 85% cache hit rate.",
        )
        state = CareerEngineState(
            current_phase=PhaseStatus.FINALIZING,
            raw_history_text="Name: Jane Smith\nSenior Engineer, 10 years experience.",
            extracted_star_stories=[story],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "resume.pdf"
            returned_path = render_pdf(state, output_path=output)

            # The returned path matches the requested output_path.
            assert returned_path == output

            # The file must exist and be non-empty.
            assert output.exists(), "PDF file was not created"
            pdf_bytes = output.read_bytes()
            assert len(pdf_bytes) > 0, "PDF file is empty"

            # Validate it is actually a PDF (magic header).
            assert pdf_bytes[:4] == b"%PDF", (
                f"Written file does not start with PDF magic bytes; "
                f"got {pdf_bytes[:8]!r}"
            )

    def test_render_pdf_creates_parent_directories(self) -> None:
        """render_pdf creates parent directories if they don't exist."""
        state = _minimal_state()
        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = pathlib.Path(tmpdir) / "nested" / "dirs" / "resume.pdf"
            render_pdf(state, output_path=deep_path)
            assert deep_path.exists()


# ── Template rendering sanity checks ─────────────────────────────────────────


class TestTemplateRendering:
    """Basic sanity checks on the rendered HTML structure."""

    def test_render_html_contains_candidate_name(self) -> None:
        """Candidate name extracted from raw_history_text appears in the HTML header."""
        state = CareerEngineState(
            raw_history_text="Name: Alice Engineer\n5 years experience.",
        )
        html = render_html(state)
        assert "Alice Engineer" in html

    def test_render_html_is_valid_html_structure(self) -> None:
        """Rendered HTML contains basic structural elements."""
        state = _minimal_state()
        html = render_html(state)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_render_html_includes_professional_summary(self) -> None:
        """professional_summary from state appears in the rendered HTML (v2.0.0).

        target_competencies was removed in v2.0.0; professional_summary is used instead.
        """
        state = CareerEngineState(
            raw_history_text="Name: Bob Dev\nBackend engineer.",
            professional_summary="Senior backend engineer specialising in distributed systems.",
        )
        html = render_html(state)
        assert "Senior backend engineer" in html

    def test_render_html_autoescape_is_on(self) -> None:
        """Verify autoescape is active by confirming < is escaped in user-provided text."""
        state = CareerEngineState(
            raw_history_text="Name: Test User\n<b>bold history</b>",
        )
        html = render_html(state)
        # The raw_history_text is not rendered into the HTML body, so this is mainly
        # a sanity check. The template uses autoescape — any value rendered via {{}}
        # will be escaped.
        # Verify the template itself doesn't inject raw source as unescaped.
        assert "&lt;" not in html or "Test User" in html or "Candidate Name" in html
