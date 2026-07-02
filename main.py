"""CareerEngine — CLI entrypoint (Phase 1).

This file is intentionally thin: it contains ONLY Click command definitions
and argument parsing.  All session logic, agent wiring, model-client
resolution, and PDF rendering live in:

    cli/app.py      — interactive CLI loop + session management
    cli/session.py  — ADK session state helpers
    integration/    — model client, auth wiring, access-mode resolution

The design keeps agent/runtime logic OUT of main.py so a Streamlit web
frontend (Phase 2) can import from cli/ and integration/ directly, reusing
the exact same wiring without touching this file.

Commands
--------
  grill   Start or continue a "Grill Me" discovery session.
  tailor  Tailor a completed resume to a job description.
"""

from __future__ import annotations

import pathlib
import sys

import click


@click.group()
def cli() -> None:
    """CareerEngine — convert raw career history into quantified STAR resumes."""
    from workflows.observability import configure_logging

    configure_logging()


@cli.command()
@click.option(
    "--history-file",
    "-f",
    type=click.Path(exists=True, readable=True, path_type=pathlib.Path),
    help="Path to a text file containing your raw career history.",
)
@click.option(
    "--output-pdf",
    "-o",
    type=click.Path(path_type=pathlib.Path),
    default=None,
    help="Optional path for the rendered PDF resume.",
)
@click.option(
    "--resume-file",
    "-r",
    type=click.Path(exists=True, readable=True, path_type=pathlib.Path),
    default=None,
    help="Path to an existing resume (PDF/PNG/JPG/WEBP) to vision-ingest as your starting timeline.",
)
@click.option(
    "--session-id",
    "-s",
    default=None,
    help="Resume an existing session by ID.",
)
@click.option(
    "--firestore",
    is_flag=True,
    default=False,
    help="Use Firestore for session persistence (requires GCP credentials).",
)
def grill(
    history_file: pathlib.Path | None,
    output_pdf: pathlib.Path | None,
    resume_file: pathlib.Path | None,
    session_id: str | None,
    firestore: bool,
) -> None:
    """Start a 'Grill Me' discovery session to extract quantified STAR stories.

    Provide your raw career history via --history-file or by piping to stdin.
    The agent will ask probing questions until concrete, metric-backed stories
    are extracted.  Every 5 turns a checkpoint verifies the progress before
    continuing.  On completion, an optional PDF resume is rendered.

    Examples::

        # From a file
        career-engine grill --history-file my_career.txt --output-pdf resume.pdf

        # From stdin (pipe)
        cat my_career.txt | career-engine grill --output-pdf resume.pdf
    """
    from cli.app import format_model_api_error, run_interactive_session
    from integration.model_client import ModelAPIError

    # ── Resolve raw history text ──────────────────────────────────────────────
    # A resume file is itself a history source, so text is optional when given.
    if history_file:
        raw_history = history_file.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw_history = sys.stdin.read()
    elif resume_file is not None:
        raw_history = ""
    else:
        click.echo(
            "No career history provided.  Use --resume-file, --history-file, or pipe text to stdin.",
            err=True,
        )
        sys.exit(1)

    if resume_file is None and not raw_history.strip():
        click.echo("Career history is empty.  Provide some text or a --resume-file.", err=True)
        sys.exit(1)

    # ── Delegate to CLI app ───────────────────────────────────────────────────
    try:
        run_interactive_session(
            raw_history=raw_history,
            output_pdf=output_pdf,
            session_id=session_id,
            use_firestore=firestore,
            resume_file=resume_file,
        )
    except ModelAPIError as exc:
        # A quota/transport failure should guide the user, not dump a stack trace.
        click.echo(format_model_api_error(exc, use_firestore=firestore), err=True)
        sys.exit(0)


@cli.command()
@click.argument("session_id")
@click.argument("jd_source")
@click.option(
    "--output-pdf",
    "-o",
    type=click.Path(path_type=pathlib.Path),
    default=None,
    help="Optional path for the tailored PDF resume.",
)
@click.option(
    "--firestore",
    is_flag=True,
    default=False,
    help="Use Firestore for session persistence.",
)
def tailor(
    session_id: str,
    jd_source: str,
    output_pdf: pathlib.Path | None,
    firestore: bool,
) -> None:
    """Tailor a completed resume to a job description.

    SESSION_ID is the ID of a completed 'grill' session.

    JD_SOURCE is either:
      - A URL (http:// or https://), which will be fetched and cleaned.
      - Raw job description text (wrap in quotes for multi-word input).

    Examples::

        career-engine tailor abc-123 https://example.com/jobs/42 -o tailored.pdf
        career-engine tailor abc-123 "Python engineer with 5+ years" -o tailored.pdf
    """
    from cli.app import format_model_api_error, run_tailor_command
    from integration.model_client import ModelAPIError

    try:
        run_tailor_command(
            session_id=session_id,
            jd_source=jd_source,
            output_pdf=output_pdf,
            use_firestore=firestore,
        )
    except ModelAPIError as exc:
        click.echo(format_model_api_error(exc, use_firestore=firestore), err=True)
        sys.exit(0)


@cli.command()
def web() -> None:
    """Launch the Streamlit web workspace (dashboard).

    Thin wrapper around ``streamlit run web/streamlit_app.py``. All UI logic
    lives in ``web/`` and reuses the same session/runner core as the CLI.
    """
    import subprocess

    app_path = pathlib.Path(__file__).parent / "web" / "streamlit_app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        check=False,
    )


if __name__ == "__main__":
    cli()
