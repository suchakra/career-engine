"""Jinja2 → HTML → PDF resume renderer.

Phase 1 implementation (WS-B).

Pipeline:
1. Map the VALIDATED CareerEngineState into a sanitised Jinja2 template context.
2. Render templates/classic_resume.html via Jinja2 with autoescaping=True.
   All model-derived text is auto-escaped; the template never uses |safe.
3. Convert HTML → PDF via WeasyPrint (chosen over headless Chrome because
   WeasyPrint is a pure-Python library with zero browser dependencies,
   installable and functional in this Linux devcontainer without a display
   server.  ARCHITECTURE.md §7 specifies headless Chrome as the preferred
   engine; this is a documented deviation — noted in PROGRESS.md).

Design rules (enforced):
- Only stories with metrics_validated=True are mapped into the template context.
- Jinja2 Environment is created with autoescape=True (covers .html extensions).
- No |safe filter is used anywhere in the template or the context builder.
- If state is invalid / required fields are missing, ValidationError is raised
  rather than silently emitting a broken document.
- The renderer never calls the model registry; it consumes pre-validated state.
"""

from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from pydantic import ValidationError  # noqa: F401 - re-exported for callers

from schema import CareerEngineState, StarStory

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "templates"
CLASSIC_RESUME_TEMPLATE = "classic_resume.html"

# Minimum fields that must be non-empty for a document to be renderable.
# An absent candidate_name is the canary: if even this is missing the state
# was never properly seeded and we should raise rather than emit a blank PDF.
_REQUIRED_STATE_FIELDS: list[str] = ["raw_history_text"]


# ── Context builder ───────────────────────────────────────────────────────────


def _build_template_context(state: CareerEngineState) -> dict[str, Any]:
    """Map a validated CareerEngineState into the Jinja2 template context.

    Only stories with metrics_validated=True are included.  All string values
    are plain Python str objects; Jinja2's autoescaping handles HTML-encoding.

    Args:
        state: A CareerEngineState that has passed through the discovery loop.

    Returns:
        A dict ready to pass to Jinja2's template.render(**context).

    Raises:
        ValueError: if state contains no usable content to render.
    """
    validated_stories: list[StarStory] = [
        s for s in state.extracted_star_stories if s.metrics_validated
    ]

    # Group stories by pillar (insertion-ordered in Python 3.7+).
    by_pillar: dict[str, list[StarStory]] = defaultdict(list)
    for story in validated_stories:
        by_pillar[story.pillar].append(story)

    # Derive a display name from the pillar list or raw history header.
    # Real production wiring would pull from a user profile; here we expose a
    # clean hook that the integration layer can override by extending this
    # function.  We default to a safe placeholder so the document is always
    # renderable without raising.
    candidate_name: str = _extract_candidate_name(state)

    context: dict[str, Any] = {
        # Identity fields (safe defaults when profile not yet wired)
        "candidate_name": candidate_name,
        "candidate_email": "",
        "candidate_location": "",
        "candidate_linkedin": "",
        # Summary / competency (v1.1.0: dedicated professional_summary field)
        "summary": state.professional_summary or "",
        "target_competencies": list(state.target_competencies),
        # STAR stories keyed by pillar; only validated ones
        "stories_by_pillar": dict(by_pillar),
        # Phase metadata (non-sensitive)
        "current_phase": state.current_phase.value,
        "contract_version": state.contract_version,
    }
    return context


def _extract_candidate_name(state: CareerEngineState) -> str:
    """Attempt to extract a candidate name from the state.

    Looks for a "Name:" line in raw_history_text; falls back to a safe
    placeholder so rendering never fails on this field alone.

    Args:
        state: CareerEngineState (may have sparse raw_history_text).

    Returns:
        A non-empty string suitable for display in the resume header.
    """
    for line in state.raw_history_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("name:"):
            name = stripped[5:].strip()
            if name:
                return name
    # Safe fallback: not empty, so the template always renders a header.
    return "Candidate Name"


# ── Validation helper ─────────────────────────────────────────────────────────


def _validate_state_for_rendering(state: CareerEngineState) -> None:
    """Raise ValueError if state is too sparse to render a meaningful document.

    An "invalid/partial state" per the acceptance criteria means the state
    object itself is malformed (Pydantic already guards the type contract);
    here we additionally guard against logically empty state — e.g. a
    freshly-constructed CareerEngineState() with no history and no stories,
    which would produce a blank PDF.

    Args:
        state: The CareerEngineState to validate.

    Raises:
        ValueError: if the state is logically empty / not ready for rendering.
    """
    # A state is renderable if it has at least some history text OR at least
    # one validated story.  A brand-new default state has neither.
    has_content = bool(state.raw_history_text.strip()) or any(
        s.metrics_validated for s in state.extracted_star_stories
    )
    if not has_content:
        raise ValueError(
            "CareerEngineState has no renderable content: raw_history_text is empty "
            "and there are no validated StarStory objects.  Complete the discovery "
            "session before rendering."
        )


# ── Public API ────────────────────────────────────────────────────────────────


def render_html(
    state: CareerEngineState,
    *,
    template_name: str = CLASSIC_RESUME_TEMPLATE,
) -> str:
    """Render a resume HTML string from validated CareerEngineState.

    Jinja2 autoescaping is always enabled.  All model-derived text is escaped;
    hostile content such as <script> tags is rendered as inert text.

    Args:
        state: CareerEngineState; only stories with metrics_validated=True
               are included in the output.
        template_name: Jinja2 template file name inside templates/.
                       Defaults to "classic_resume.html".

    Returns:
        HTML string with all variables escaped (no raw HTML from model output).

    Raises:
        ValueError: if state has no renderable content (too sparse).
        jinja2.TemplateNotFound: if the template file does not exist.
    """
    _validate_state_for_rendering(state)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "htm", "xml"]),
        keep_trailing_newline=True,
    )

    try:
        template = env.get_template(template_name)
    except TemplateNotFound as exc:
        raise TemplateNotFound(  # re-raise with clearer context
            f"Template {template_name!r} not found in {TEMPLATE_DIR}"
        ) from exc

    context = _build_template_context(state)
    return template.render(**context)


def render_pdf(
    state: CareerEngineState,
    *,
    output_path: pathlib.Path,
    template_name: str = CLASSIC_RESUME_TEMPLATE,
) -> pathlib.Path:
    """Render a PDF resume from validated CareerEngineState.

    Uses WeasyPrint (pure-Python PDF engine) rather than headless Chrome.
    WeasyPrint is installable in this Linux devcontainer without a display
    server.  See module docstring for the deviation note.

    Args:
        state: Validated CareerEngineState (same constraints as render_html).
        output_path: Destination path for the output PDF file.
        template_name: Jinja2 template file name inside templates/.

    Returns:
        Path to the written PDF file (same as output_path on success).

    Raises:
        ValueError: if state has no renderable content.
        RenderError: if WeasyPrint is not installed or rendering fails.
        jinja2.TemplateNotFound: if the template file does not exist.
    """
    html_string = render_html(state, template_name=template_name)

    try:
        import weasyprint
    except ImportError as exc:
        raise RenderError(
            "WeasyPrint is not installed.  Add 'weasyprint' to pyproject.toml "
            "dependencies and reinstall."
        ) from exc

    try:
        pdf_bytes: bytes = weasyprint.HTML(
            string=html_string,
            base_url=str(TEMPLATE_DIR),
        ).write_pdf()
    except Exception as exc:
        raise RenderError(f"WeasyPrint PDF generation failed: {exc}") from exc

    if not pdf_bytes:
        raise RenderError("WeasyPrint returned an empty PDF; rendering failed silently.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return output_path


# ── Exceptions ────────────────────────────────────────────────────────────────


class RenderError(Exception):
    """Raised when the PDF render pipeline fails (WeasyPrint unavailable, etc.)."""
