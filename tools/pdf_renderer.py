"""Jinja2 → HTML → PDF resume renderer — typed stub.

Phase 0 — interface only.  Phase 1 (WS-B) implements the bodies.

Pipeline:
1. Map the VALIDATED CareerEngineState into a Jinja2 template context.
2. Render templates/classic_resume.html via Jinja2 (with autoescaping=True).
3. Convert the HTML to PDF via headless Chrome (via subprocess or a library).

Design rules:
- Only VALIDATED state (metrics_validated=True stories) feeds the template.
- Jinja2 autoescaping is ALWAYS enabled; model output is never trusted as HTML.
- If state is invalid or required fields are missing, raise a ValidationError
  rather than silently emitting a broken document.
- The renderer never calls the model registry — it consumes pre-validated state.
"""

from __future__ import annotations

import pathlib

from schema import CareerEngineState

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "templates"
CLASSIC_RESUME_TEMPLATE = "classic_resume.html"


def render_html(state: CareerEngineState, *, template_name: str = CLASSIC_RESUME_TEMPLATE) -> str:
    """Render a resume HTML string from validated CareerEngineState.

    Args:
        state: Validated CareerEngineState; only stories with metrics_validated=True
               are included in the output.
        template_name: Jinja2 template file name inside templates/.

    Returns:
        Escaped, rendered HTML string.

    Raises:
        ValidationError: if state lacks the minimum required fields.
        TemplateNotFoundError: if the template file does not exist.
    """
    raise NotImplementedError("pdf_renderer.render_html is a Phase 1 task.")


def render_pdf(
    state: CareerEngineState,
    *,
    output_path: pathlib.Path,
    template_name: str = CLASSIC_RESUME_TEMPLATE,
) -> pathlib.Path:
    """Render a PDF resume from validated CareerEngineState.

    Calls render_html() then converts via headless Chrome.

    Args:
        state: Validated CareerEngineState.
        output_path: Destination path for the output PDF file.
        template_name: Jinja2 template file name inside templates/.

    Returns:
        Path to the written PDF file.

    Raises:
        ValidationError: if state lacks the minimum required fields.
        RenderError: if headless Chrome fails or is not installed.
    """
    raise NotImplementedError("pdf_renderer.render_pdf is a Phase 1 task.")


class RenderError(Exception):
    """Raised when the PDF render pipeline fails (headless Chrome unavailable, etc.)."""
