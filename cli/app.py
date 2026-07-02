"""CareerEngine CLI session driver — Phase 1 integration.

Implements the multi-turn "Grill Me" loop as a CLI conversation.  All agent
/ runner wiring lives here; ``main.py`` is a thin Click entrypoint that
delegates to the public functions in this module.

Design rules:
- No Streamlit imports (Phase 2 web frontend reuses integration/ directly).
- No hardcoded model names (all resolved via models.registry).
- State is managed through the ADK session service (InMemorySessionService
  for dev/CI; FirestoreSessionService for production).
- Access-mode resolution: FREE uses the platform Gemini key;
  BYOK fetches from the SecretManager KeyVault.
- PDF rendering is called on COMPLETE via tools.pdf_renderer.render_pdf.

Multi-turn Runner interaction
-----------------------------
The ADK Workflow graph (discovery_graph.py) always runs from START on every
``runner.run_async`` call.  For CLI multi-turn sessions this means:

  1. Ingest only runs on the first (INGESTING) turn — the graph-entry shim
     gates it so it seeds the ``work_timeline`` once.  Later turns pass the
     seeded state straight through.  The ``work_timeline`` and
     ``extracted_star_stories`` from prior turns ARE in the flat session
     state, so subsequent nodes see the accumulated progress.

  2. The CLI sets ``pending_user_answer`` in the session state BEFORE calling
     ``run_async``.  The grill node reads that field; if populated it runs
     metric extraction, otherwise it generates the opening question.

  3. After ``run_async`` returns, the CLI reads ``current_question`` to print
     for the user, and ``checkpoint_delta_summary`` when the phase becomes
     CHECKPOINT.

  4. The 5-turn checkpoint: when ``current_phase == CHECKPOINT``, the CLI
     prints the summary, asks the user to confirm, sets
     ``checkpoint_verified=True``, and calls ``run_async`` again.  The
     checkpoint node detects the flag and advances back to GRILLING.

  5. On COMPLETE, ``finalize_master_resume_node`` has set
     ``professional_summary`` and ``master_resume_json``; the CLI calls
     ``render_pdf``.
"""

from __future__ import annotations

import mimetypes
import pathlib
import sys
import uuid
from collections.abc import Callable
from datetime import date
from typing import cast

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService

import cli.prefs as prefs
import cli.session as session_helpers
from config import AccessMode, get_settings
from integration.model_client import GeminiModelClient, ModelAPIError, build_model_client
from schema import (
    CareerEngineState,
    Entry,
    EntryStatus,
    PhaseStatus,
    UpgradeRequired,
    discovery_completeness,
    recent_window_complete,
)
from tools.pdf_renderer import render_pdf
from tools.resume_parser import ParseError, parse_resume
from workflows.discovery_graph import build_runner
from workflows.nodes import set_model_client_factory

# ── Resume-file ingestion (Phase 1.7-A) ───────────────────────────────────────

_RESUME_EXT_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def guess_resume_mime(path: pathlib.Path) -> str:
    """Best-effort MIME type for a resume file from its extension.

    Falls back to ``mimetypes`` then ``application/octet-stream`` (which
    ``parse_resume`` rejects with a clear ParseError).
    """
    mime = _RESUME_EXT_MIME.get(path.suffix.lower())
    if mime:
        return mime
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def parse_resume_file(path: pathlib.Path, *, client: GeminiModelClient) -> list[Entry]:
    """Read a resume file and parse it into a work_timeline (Phase 1.7-A).

    The raw bytes are read here at the CLI boundary, passed straight to the
    vision parser, and never stored — only the returned Entries persist.

    Args:
        path: Path to a PDF or image resume file.
        client: The resolved multimodal model client.

    Returns:
        The parsed list of Entry objects.

    Raises:
        ParseError: if the file is empty, an unsupported type, or unparseable.
        OSError: if the file cannot be read.
    """
    data = path.read_bytes()
    return parse_resume(data, guess_resume_mime(path), client=client)

# ── Runner / session assembly ─────────────────────────────────────────────────


def build_session_service(*, use_firestore: bool = False) -> BaseSessionService:
    """Return an ADK session service.

    For offline / dev / CI runs, returns ``InMemorySessionService`` (no GCP
    needed).  Production wires in ``FirestoreSessionService``.

    Args:
        use_firestore: If ``True``, attempt to build a Firestore-backed service.
            Falls back to in-memory if the Firestore client is unavailable.

    Returns:
        A ``BaseSessionService`` instance.
    """
    if use_firestore:
        try:
            from database.firestore_session import FirestoreSessionService

            return FirestoreSessionService()
        except Exception as exc:
            # GCP not available — fall through to in-memory, but make the
            # downgrade LOUD (REVIEW.md #3): a silent fallback violates the
            # user's persistence expectation.  The environment-aware hard-stop
            # policy (prod / explicit use_firestore must fail, not downgrade)
            # lands in Phase 2 — see REVIEW.md §5 OQ1.
            print(
                "⚠  Firestore was requested but is unavailable "
                f"({type(exc).__name__}: {exc}).\n"
                "⚠  Falling back to IN-MEMORY session storage — "
                "nothing will be persisted across runs.",
                file=sys.stderr,
            )
    return cast("BaseSessionService", InMemorySessionService())  # type: ignore[no-untyped-call]


def _install_model_client(client: GeminiModelClient) -> None:
    """Inject the model client into the workflow nodes and expose it for scrapers.

    Sets the nodes factory so every node call uses the same real client.

    Args:
        client: The resolved ``GeminiModelClient`` for this session.
    """
    set_model_client_factory(lambda: client)


def resolve_auth_and_client() -> tuple[str, AccessMode, GeminiModelClient]:
    """Resolve user identity, access mode, and model client for a CLI session.

    Uses the dev escape hatch (``settings.dev_user_id`` + ``settings.dev_gemini_key``)
    for offline runs; falls through to ``CliAuthProvider`` + ``SecretManagerKeyVault``
    for real sessions.

    Returns:
        A ``(user_id, access_mode, client)`` triple.
    """
    settings = get_settings()

    # ── Dev escape hatch (no network) ────────────────────────────────────────
    if settings.dev_user_id:
        user_id = settings.dev_user_id
        # Dev mode: FREE if no dev key, otherwise BYOK-like with the dev key
        if settings.dev_gemini_key:
            api_key: str | None = settings.dev_gemini_key
            access_mode = AccessMode.BYOK
        elif settings.gemini_api_key:
            api_key = settings.gemini_api_key
            access_mode = AccessMode.FREE
        else:
            api_key = None
            access_mode = AccessMode.FREE
        client = GeminiModelClient(api_key=api_key)
        return user_id, access_mode, client

    # ── Real OAuth path ───────────────────────────────────────────────────────
    from auth.cli_auth import CliAuthProvider, resolve_access_mode
    from auth.key_vault import SecretManagerKeyVault

    auth = CliAuthProvider()
    user_id = auth.get_user_id()
    vault = SecretManagerKeyVault()
    access_mode = resolve_access_mode(user_id, vault)
    client = build_model_client(
        user_id=user_id,
        key_vault=vault,
        access_mode=access_mode,
    )
    return user_id, access_mode, client


# ── Session-level loop ────────────────────────────────────────────────────────


class DiscoverySession:
    """Manages a single CareerEngine discovery session from the CLI.

    Encapsulates:
    - The ADK Runner wired to the discovery workflow.
    - The session service (in-memory or Firestore).
    - User identity and access mode.
    - The turn-by-turn conversation loop.

    Args:
        user_id: The authenticated user's stable platform ID.
        access_mode: ``FREE`` or ``BYOK``.
        model_client: The resolved Gemini model client.
        session_service: ADK session service to use.
        app_name: ADK application name.
        session_id: Optional caller-supplied session ID.  A UUID is generated
            if not provided.
    """

    def __init__(
        self,
        *,
        user_id: str,
        access_mode: AccessMode,
        model_client: GeminiModelClient,
        session_service: BaseSessionService,
        app_name: str = "career_engine_discovery",
        session_id: str | None = None,
    ) -> None:
        """Initialise the discovery session."""
        self._user_id = user_id
        self._access_mode = access_mode
        self._client = model_client
        self._svc = session_service
        self._app_name = app_name
        self._session_id = session_id or str(uuid.uuid4())
        self._runner: Runner = build_runner(
            session_service=session_service,
            app_name=app_name,
        )
        self._turn_index = 0  # in-memory turn ordinal for observability spans
        # Inject model client into the workflow nodes.
        _install_model_client(model_client)

    @property
    def session_id(self) -> str:
        """The ADK session ID for this discovery session."""
        return self._session_id

    @property
    def user_id(self) -> str:
        """The authenticated user's stable platform ID."""
        return self._user_id

    @property
    def access_mode(self) -> AccessMode:
        """The resolved access mode (FREE or BYOK)."""
        return self._access_mode

    @property
    def model_client(self) -> GeminiModelClient:
        """The Gemini model client used for inference."""
        return self._client

    async def start(
        self,
        raw_history_text: str,
        *,
        reference_date: str = "",
        work_timeline: list[Entry] | None = None,
    ) -> str:
        """Create the ADK session and run the first turn (ingest + opening question).

        Args:
            raw_history_text: The user's raw career history (multi-decade text).
            reference_date: ISO ``YYYY-MM-DD`` injected clock for the session
                (stamped by the CLI boundary; nodes never call ``datetime.now``).
            work_timeline: Optional pre-parsed entries (vision ingest) to seed
                instead of parsing ``raw_history_text``.

        Returns:
            The opening question from the grill node, or an empty string if the
            workflow terminated immediately (e.g. no active gaps after ingest).
        """
        initial_state = CareerEngineState(
            raw_history_text=raw_history_text,
            reference_date=reference_date,
            work_timeline=list(work_timeline) if work_timeline else [],
        )
        await session_helpers.create_session(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
            initial_state=initial_state,
        )
        await self._run_turn()
        state = await session_helpers.read_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )
        return state.current_question

    async def answer(self, user_answer: str) -> TurnResult:
        """Submit a user answer and run one grill turn.

        Injects ``pending_user_answer`` into the session state, runs the
        workflow, then returns a ``TurnResult`` describing what happened.

        Args:
            user_answer: The user's answer to the most recent question.

        Returns:
            A ``TurnResult`` with the next question, checkpoint summary (if
            at turn 5), or a signal that the session is complete.
        """
        await session_helpers.patch_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
            pending_user_answer=user_answer,
        )
        await self._run_turn()
        return await self._read_turn_result()

    async def confirm_checkpoint(self) -> str:
        """Confirm the checkpoint and resume grilling.

        Called after the user has reviewed the ``checkpoint_delta_summary``
        and confirmed it is accurate.  Sets ``checkpoint_verified=True``,
        re-runs the workflow, and returns the next question.

        Returns:
            The next grill question, or empty string if the session is now
            complete.
        """
        await session_helpers.patch_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
            checkpoint_verified=True,
        )
        await self._run_turn()
        state = await session_helpers.read_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )
        return state.current_question

    async def advance(self) -> TurnResult:
        """Advance the workflow by one turn WITHOUT supplying a user answer.

        Used by the CLI driver to run a non-interactive turn — e.g. once the
        last competency gap is closed (grill is terminal-per-turn, so the
        finalize node runs on the FOLLOWING turn).  Injects no human input.

        Returns:
            A ``TurnResult`` describing the state after the turn.
        """
        await self._run_turn()
        return await self._read_turn_result()

    async def current_state(self) -> CareerEngineState:
        """Return the current CareerEngineState for this session.

        Returns:
            The validated CareerEngineState from the session service.
        """
        return await session_helpers.read_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )

    async def resume_state(self) -> CareerEngineState | None:
        """Return this session's persisted state if it exists, else None.

        Used by the resume path (Phase 1.7-B) to reuse an existing session
        instead of clobbering it with a fresh ``start``.  Returns ``None`` when
        no session has been persisted under this id.
        """
        return await session_helpers.get_session_state_if_exists(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )

    async def render_resume_pdf(self, output_path: pathlib.Path) -> pathlib.Path:
        """Render the finalised master resume to a PDF file.

        Should only be called after the session reaches ``COMPLETE`` phase.

        Args:
            output_path: Destination path for the PDF.

        Returns:
            The path of the written PDF (same as ``output_path``).

        Raises:
            ValueError: if the session is not yet complete or has no content.
        """
        state = await self.current_state()
        if state.current_phase != PhaseStatus.COMPLETE:
            raise ValueError(
                f"Session is not complete (phase={state.current_phase.value!r}). "
                "Finish the discovery session before rendering a PDF."
            )
        return render_pdf(state, output_path=output_path)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _run_turn(self) -> None:
        """Execute one Runner turn, draining all events (timed + logged).

        Uses an in-memory turn ordinal for the span (no extra state read); the
        callers read state after the turn, so a pre-flight read would be a
        redundant Firestore round-trip in production.
        """
        from workflows.observability import get_logger, log_operation

        self._turn_index += 1
        with log_operation(
            "graph.turn",
            logger=get_logger("session"),
            turn=self._turn_index,
            session_id=self._session_id,
        ):
            async for _ in self._runner.run_async(
                user_id=self._user_id,
                session_id=self._session_id,
                state_delta={},
            ):
                pass

    async def _read_turn_result(self) -> TurnResult:
        """Read state after a grill turn and build a TurnResult.

        Reads the RAW session state (not the schema-validated view) so the real
        ``_upgrade_required`` side-channel signal written by the grill shim is
        visible — see ``TurnResult.from_state`` (REVIEW.md #1).
        """
        raw = await session_helpers.read_raw_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )
        state = CareerEngineState.model_validate(raw)
        return TurnResult.from_state(state, upgrade_signal=raw.get("_upgrade_required"))


class TurnResult:
    """Describes the outcome of one grill turn.

    Attributes:
        phase: The current session phase after the turn.
        next_question: The question to show the user (if grilling continues).
        checkpoint_summary: Non-empty when a 5-turn checkpoint was reached.
        is_complete: True when the session has reached the COMPLETE phase.
        upgrade_required: True if the REASONING_HIGH capability is unavailable.
        upgrade_message: The ready-to-display message from the UpgradeRequired
            signal (empty unless ``upgrade_required`` is True).
        stories_count: Number of validated StarStories so far.
    """

    def __init__(
        self,
        *,
        phase: PhaseStatus,
        next_question: str,
        checkpoint_summary: str,
        is_complete: bool,
        upgrade_required: bool,
        stories_count: int,
        upgrade_message: str = "",
    ) -> None:
        """Initialise a TurnResult."""
        self.phase = phase
        self.next_question = next_question
        self.checkpoint_summary = checkpoint_summary
        self.is_complete = is_complete
        self.upgrade_required = upgrade_required
        self.upgrade_message = upgrade_message
        self.stories_count = stories_count

    @classmethod
    def from_state(
        cls,
        state: CareerEngineState,
        *,
        upgrade_signal: str | None = None,
    ) -> TurnResult:
        """Build a TurnResult from a CareerEngineState.

        The upgrade-required outcome is read from the REAL side-channel the
        grill shim writes — ``ctx.state["_upgrade_required"]`` (a serialized
        ``UpgradeRequired``) — passed in as ``upgrade_signal``.  This replaces
        the old, effectively-dead heuristic that string-matched the literal
        token in ``current_question`` (REVIEW.md #1).  The v2.0.0 contract
        promotes this to a typed state field; this is the v1.1.x band-aid.

        Args:
            state: The CareerEngineState after the most recent turn.
            upgrade_signal: The raw ``_upgrade_required`` JSON value from the
                unvalidated session state, or ``None`` if absent.

        Returns:
            A populated TurnResult.
        """
        upgrade_required = bool(upgrade_signal)
        upgrade_message = ""
        if upgrade_signal:
            try:
                upgrade_message = UpgradeRequired.model_validate_json(
                    upgrade_signal
                ).user_message
            except ValueError:
                # Malformed signal — still surface the upgrade path, just with
                # no specific message rather than crashing the turn read.
                upgrade_message = ""
        return cls(
            phase=state.current_phase,
            next_question=state.current_question,
            checkpoint_summary=state.checkpoint_delta_summary,
            is_complete=(state.current_phase == PhaseStatus.COMPLETE),
            upgrade_required=upgrade_required,
            upgrade_message=upgrade_message,
            stories_count=len(
                [s for s in state.extracted_star_stories if s.metrics_validated]
            ),
        )

    def __repr__(self) -> str:
        """Return a debug string."""
        return (
            f"TurnResult(phase={self.phase.value!r}, "
            f"is_complete={self.is_complete}, "
            f"stories={self.stories_count}, "
            f"question={self.next_question[:40]!r})"
        )


# ── Progressive discovery: meter, nudge, return loop (Phase 1.5) ──────────────
#
# Core principle: discovery is a NUDGE, never a gate.  Applying / tailoring is
# NEVER blocked by an incomplete window — these helpers only inform and offer.

_NUDGE_MESSAGE = (
    "Tailored resumes come out noticeably stronger once the rest of your recent "
    "history is filled in. You can keep going now or pick it up later — "
    "applying is never blocked."
)


def discovery_nudge_message() -> str:
    """Return the consent-respecting discovery nudge text (shared by CLI + web)."""
    return _NUDGE_MESSAGE


def _today_iso() -> str:
    """Return today's date as ISO ``YYYY-MM-DD``.

    This is the ONLY place a wall clock is read; logic everywhere else takes an
    injected ``today`` / uses ``state.reference_date`` so behavior is testable.
    """
    return date.today().isoformat()


def _year_of(date_str: str) -> int | None:
    """Extract the year from a YYYY-MM / YYYY string; None on failure."""
    if not date_str:
        return None
    try:
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


def _portfolio_depth_years(state: CareerEngineState) -> int:
    """Span in years from the earliest entry start to ``reference_date``."""
    ref = _year_of(state.reference_date)
    starts = [y for y in (_year_of(e.start_date) for e in state.work_timeline) if y is not None]
    if ref is None or not starts:
        return 0
    return max(0, ref - min(starts))


def render_progress_meter(state: CareerEngineState) -> str:
    """Render the discovery progress meter from the derived schema helpers.

    Pure read of ``discovery_completeness`` (over the trailing-5-year window,
    using ``state.reference_date``) plus the portfolio depth.  No clock access.
    """
    pct = round(discovery_completeness(state) * 100)
    depth = _portfolio_depth_years(state)
    return f"Recent 5-yr window: {pct}% documented · portfolio depth: {depth} yrs"


def should_show_nudge(
    state: CareerEngineState, *, today: str, prefs_path: pathlib.Path | None = None
) -> bool:
    """Return True if the discovery nudge should be shown (never a gate).

    Shown when the recent window is incomplete AND the user has not snoozed it.
    """
    if recent_window_complete(state):
        return False
    return not prefs.is_snoozed(today, path=prefs_path)


def emit_nudge_if_needed(
    state: CareerEngineState,
    *,
    today: str,
    prefs_path: pathlib.Path | None = None,
    out: Callable[[str], None] = print,
) -> bool:
    """Print the consent-respecting nudge if warranted.  Returns whether shown.

    The caller's action ALWAYS proceeds regardless of the return value — this
    only emits a message.
    """
    if not should_show_nudge(state, today=today, prefs_path=prefs_path):
        return False
    out(f"\n💡 {_NUDGE_MESSAGE}")
    return True


def resumable_entries(state: CareerEngineState) -> list[Entry]:
    """Pending entries older than the current frontier (return-loop candidates).

    These are entries still needing work (``needs_quantifying`` / ``documented``)
    that sit behind the grill frontier — i.e. the backward continuation a return
    session would pick up.  With no frontier set, all pending entries qualify.
    """
    pending = [
        e
        for e in state.work_timeline
        if e.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED)
    ]
    if not state.grill_frontier:
        return pending
    frontier = next(
        (e for e in state.work_timeline if str(e.entry_id) == state.grill_frontier),
        None,
    )
    if frontier is None:
        return pending
    fy = _year_of(frontier.start_date)
    out: list[Entry] = []
    for e in pending:
        if str(e.entry_id) == state.grill_frontier:
            continue
        ey = _year_of(e.start_date)
        if fy is None or ey is None or ey <= fy:
            out.append(e)
    return out


def has_resumable_work(state: CareerEngineState) -> bool:
    """Return True if there is older pending work to continue (return loop)."""
    return bool(resumable_entries(state))


async def run_return_loop(session: DiscoverySession, *, accept: bool) -> bool:
    """Offer to continue grilling older roles backward from the frontier.

    Reuses the entry-based grill loop (which already advances backward via
    ``grill_frontier``) by driving one turn through the Runner.  Does nothing if
    there is no resumable work or the user declines.  Returns whether a grill
    turn was driven.

    Args:
        session: The active discovery session.
        accept: The user's decision (injected; the CLI reads it from a prompt).
    """
    state = await session.current_state()
    if not has_resumable_work(state) or not accept:
        return False
    await session.advance()
    return True


# ── Interactive CLI loop ──────────────────────────────────────────────────────


def format_model_api_error(exc: ModelAPIError, *, use_firestore: bool) -> str:
    """Render a friendly, non-crashing message for a model API failure.

    Used by the CLI entrypoints to turn a quota/transport error into guidance
    instead of a stack trace.
    """
    if exc.is_rate_limited:
        retry = (
            f" Try again in ~{exc.retry_after_seconds:.0f}s."
            if exc.retry_after_seconds
            else ""
        )
        resume = (
            "Your progress is saved — re-run with --firestore and the session id shown "
            "above to continue."
            if use_firestore
            else "Tip: run with --firestore (and --session-id) so progress is saved and resumable."
        )
        return (
            f"\n⏳ Gemini rate limit / quota reached.{retry}\n{resume}\n"
            "(Free tier is limited to 5 requests/min and 20/day; a paid key or higher "
            "quota removes this.)"
        )
    return (
        f"\n⚠️  Model API error: {exc}\n"
        "(Any progress up to the last completed turn is saved if you used --firestore.)"
    )


def run_interactive_session(
    *,
    raw_history: str,
    output_pdf: pathlib.Path | None = None,
    session_id: str | None = None,
    use_firestore: bool = False,
    resume_file: pathlib.Path | None = None,
) -> None:
    """Run a full interactive discovery session in the terminal.

    Implements the CLI grill loop:
    1. Ingest raw history (or a parsed resume file, if ``resume_file`` is given).
    2. Print each question; read the user's answer from stdin.
    3. At the 5-turn checkpoint, print the summary and ask for confirmation.
    4. On COMPLETE, render a PDF if ``output_pdf`` is provided.

    Args:
        raw_history: Raw career history text (may be multi-line or empty when a
            resume file is supplied).
        output_pdf: Optional path to write the final PDF resume.
        session_id: Optional caller-supplied session ID (treated as resume intent).
        use_firestore: If ``True``, use Firestore for session persistence.
        resume_file: Optional PDF/image resume to vision-parse and seed the
            timeline from (fresh sessions only).  Parse failures are surfaced
            and the session continues from text instead of crashing.
    """
    import asyncio

    user_id, access_mode, client = resolve_auth_and_client()
    svc = build_session_service(use_firestore=use_firestore)

    session = DiscoverySession(
        user_id=user_id,
        access_mode=access_mode,
        model_client=client,
        session_service=svc,
        session_id=session_id,
    )

    print(f"\nCareerEngine — discovery session ({access_mode.value} mode)")
    print(f"Session: {session.session_id}")
    print("=" * 60)

    # ── Start or resume (stamp the injected clock here) ──────────────────────
    # An explicit --session-id means "resume": load the persisted session and
    # continue from where it left off rather than clobbering it (Phase 1.7-B).
    # No --session-id means a fresh session (auto id) → ingest + opening question.
    today = _today_iso()
    resumed = False
    if session_id is not None:
        existing = asyncio.run(session.resume_state())
        if existing is None:
            print(
                f"\nNo saved session {session_id!r} was found"
                + (" (Firestore session storage is required to resume across runs)."
                   if not use_firestore else ".")
                + "\nStart a new session by omitting --session-id.",
                file=sys.stderr,
            )
            return
        resumed = True
        question = existing.current_question
    else:
        # Fresh session: optionally seed the timeline from a vision-parsed resume.
        seed_timeline: list[Entry] | None = None
        if resume_file is not None:
            try:
                seed_timeline = parse_resume_file(resume_file, client=client)
                print(f"Parsed {len(seed_timeline)} entr(y/ies) from {resume_file.name}.")
            except (ParseError, OSError) as exc:
                print(
                    f"\nCouldn't read resume {resume_file.name!r}: {exc}\n"
                    "Continuing without it — type your career history when prompted.",
                    file=sys.stderr,
                )
                seed_timeline = None
        question = asyncio.run(
            session.start(raw_history, reference_date=today, work_timeline=seed_timeline)
        )

    # ── Progressive discovery: progress meter + consent-respecting nudge ─────
    launch_state = asyncio.run(session.current_state())
    print(render_progress_meter(launch_state))
    emit_nudge_if_needed(launch_state, today=today)

    # ── Return loop (resumed sessions only): offer to continue older roles ───
    # Applying is never gated; declining proceeds straight into the normal loop.
    if resumed and has_resumable_work(launch_state):
        choice = input(
            "\nPick up where you left off on older roles? [Y/n]: "
        ).strip().lower()
        if asyncio.run(run_return_loop(session, accept=choice in ("", "y", "yes"))):
            question = asyncio.run(session.current_state()).current_question

    while True:
        if not question:
            # Session ended or no question surfaced — check phase
            state = asyncio.run(session.current_state())
            if state.current_phase == PhaseStatus.COMPLETE:
                break
            # No question and all gaps closed → drive the finalize turn.
            # (grill is terminal-per-turn, so finalize runs on the NEXT turn.)
            result = asyncio.run(session.advance())
            if result.is_complete:
                break
            question = result.next_question
            _cur = asyncio.run(session.current_state())
            _pending = any(
                e.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED)
                for e in _cur.work_timeline
            )
            if not question and not _pending:
                # No pending entries and no question → keep advancing to finalize.
                continue
            if not question:
                # Still nothing — session may be stuck; exit gracefully
                print("\n[No question surfaced; ending session]")
                break

        # ── Checkpoint ───────────────────────────────────────────────────────
        state = asyncio.run(session.current_state())
        if state.current_phase == PhaseStatus.CHECKPOINT and state.checkpoint_delta_summary:
            print("\n── CHECKPOINT ──────────────────────────────────────────")
            print(state.checkpoint_delta_summary)
            print("────────────────────────────────────────────────────────")
            confirm = input("\nDoes the above look accurate? [y/N]: ").strip().lower()
            if confirm in ("y", "yes"):
                question = asyncio.run(session.confirm_checkpoint())
                continue
            else:
                print("Session paused at checkpoint.  Run again to continue.")
                return

        # ── Print question and read answer ───────────────────────────────────
        print(f"\n{question}")
        try:
            user_answer = input("\nYour answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSession interrupted.  Progress is saved.")
            return

        if not user_answer:
            print("[Empty answer — please type a response]")
            continue

        # ── Submit answer ────────────────────────────────────────────────────
        result = asyncio.run(session.answer(user_answer))
        question = result.next_question

        if result.upgrade_required:
            message = result.upgrade_message or (
                "This task requires a paid Gemini model. "
                "Set DEV_GEMINI_KEY or provide your BYOK key to continue."
            )
            print(f"\n[Upgrade required]: {message}")
            return

        if result.is_complete:
            break

    # ── Finalise ─────────────────────────────────────────────────────────────
    state = asyncio.run(session.current_state())
    print("\n" + "=" * 60)
    print("Session complete!")
    print(f"  Validated stories: {sum(1 for s in state.extracted_star_stories if s.metrics_validated)}")
    if state.professional_summary:
        print(f"\nProfessional summary:\n{state.professional_summary}")

    if output_pdf:
        try:
            path = asyncio.run(session.render_resume_pdf(output_pdf))
            print(f"\nResume PDF written to: {path}")
        except Exception as exc:
            print(f"\n[PDF render failed]: {exc}", file=sys.stderr)


def run_tailor_command(
    *,
    session_id: str,
    jd_source: str,
    output_pdf: pathlib.Path | None = None,
    use_firestore: bool = False,
) -> None:
    """Tailor the master resume to a job description URL or plain text.

    Args:
        session_id: The completed discovery session to tailor from.
        jd_source: Either a URL (starts with http/https) or raw JD text.
        output_pdf: Optional path to write the tailored PDF.
        use_firestore: If ``True``, use Firestore for session persistence.
    """
    import asyncio

    user_id, _access_mode, client = resolve_auth_and_client()
    svc = build_session_service(use_firestore=use_firestore)

    # Resolve the JD text
    if jd_source.startswith(("http://", "https://")):
        from tools.web_scraper import scrape_job_description

        print(f"Fetching JD from {jd_source!r} ...")
        jd_text = scrape_job_description(jd_source, client=client)
    else:
        jd_text = jd_source

    # Consent-respecting nudge — tailoring is NEVER blocked by an incomplete
    # window; we only inform.  The tailor proceeds regardless of the nudge.
    try:
        pre_state = asyncio.run(
            session_helpers.read_state(
                session_service=svc,
                app_name="career_engine_discovery",
                user_id=user_id,
                session_id=session_id,
            )
        )
        emit_nudge_if_needed(pre_state, today=_today_iso())
    except ValueError:
        pass  # no prior session state to evaluate; proceed to tailor

    # Patch jd_text into the session state and run the tailor node
    async def _tailor() -> CareerEngineState:
        await session_helpers.patch_state(
            session_service=svc,
            app_name="career_engine_discovery",
            user_id=user_id,
            session_id=session_id,
            jd_text=jd_text,
        )
        # Run one turn; the router will see phase=COMPLETE and go to finalize
        # which then chains to tailor.
        runner = build_runner(session_service=svc)
        _install_model_client(client)
        async for _ in runner.run_async(user_id=user_id, session_id=session_id, state_delta={}):
            pass
        return await session_helpers.read_state(
            session_service=svc,
            app_name="career_engine_discovery",
            user_id=user_id,
            session_id=session_id,
        )

    state = asyncio.run(_tailor())

    if state.tailored_resume_json:
        print("\nTailored resume JSON ready.")
        if output_pdf:
            path = render_pdf(state, output_path=output_pdf)
            print(f"Tailored PDF written to: {path}")
    else:
        print("[Warning] Tailor node produced no output.")
