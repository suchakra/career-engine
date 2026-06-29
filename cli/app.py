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

  1. Ingest re-runs each turn.  This is benign: the ingest node is
     idempotent-like — it re-reads raw_history_text and re-seeds pillars.
     The active_gaps and extracted_star_stories from prior turns ARE in the
     flat session state, so subsequent nodes see the accumulated progress.

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

import pathlib
import sys
import uuid
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from typing import cast

import cli.session as session_helpers
from config import AccessMode, get_settings
from integration.model_client import GeminiModelClient, build_model_client
from schema import CareerEngineState, PhaseStatus
from tools.pdf_renderer import render_pdf
from workflows.discovery_graph import build_runner
from workflows.nodes import set_model_client_factory


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
        except Exception:
            # GCP not available — fall through to in-memory
            pass
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

    async def start(self, raw_history_text: str) -> str:
        """Create the ADK session and run the first turn (ingest + opening question).

        Args:
            raw_history_text: The user's raw career history (multi-decade text).

        Returns:
            The opening question from the grill node, or an empty string if the
            workflow terminated immediately (e.g. no active gaps after ingest).
        """
        initial_state = CareerEngineState(raw_history_text=raw_history_text)
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

    async def answer(self, user_answer: str) -> "TurnResult":
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
        """Execute one Runner turn, draining all events."""
        async for _ in self._runner.run_async(
            user_id=self._user_id,
            session_id=self._session_id,
            state_delta={},
        ):
            pass

    async def _read_turn_result(self) -> "TurnResult":
        """Read state after a grill turn and build a TurnResult."""
        state = await session_helpers.read_state(
            session_service=self._svc,
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )
        return TurnResult.from_state(state)


class TurnResult:
    """Describes the outcome of one grill turn.

    Attributes:
        phase: The current session phase after the turn.
        next_question: The question to show the user (if grilling continues).
        checkpoint_summary: Non-empty when a 5-turn checkpoint was reached.
        is_complete: True when the session has reached the COMPLETE phase.
        upgrade_required: True if the REASONING_HIGH capability is unavailable.
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
    ) -> None:
        """Initialise a TurnResult."""
        self.phase = phase
        self.next_question = next_question
        self.checkpoint_summary = checkpoint_summary
        self.is_complete = is_complete
        self.upgrade_required = upgrade_required
        self.stories_count = stories_count

    @classmethod
    def from_state(cls, state: CareerEngineState) -> "TurnResult":
        """Build a TurnResult from a CareerEngineState.

        Args:
            state: The CareerEngineState after the most recent turn.

        Returns:
            A populated TurnResult.
        """
        upgrade_required = bool(state.current_question) and "_upgrade_required" in (
            state.current_question or ""
        )
        return cls(
            phase=state.current_phase,
            next_question=state.current_question,
            checkpoint_summary=state.checkpoint_delta_summary,
            is_complete=(state.current_phase == PhaseStatus.COMPLETE),
            upgrade_required=upgrade_required,
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


# ── Interactive CLI loop ──────────────────────────────────────────────────────


def run_interactive_session(
    *,
    raw_history: str,
    output_pdf: pathlib.Path | None = None,
    session_id: str | None = None,
    use_firestore: bool = False,
) -> None:
    """Run a full interactive discovery session in the terminal.

    Implements the CLI grill loop:
    1. Ingest raw history.
    2. Print each question; read the user's answer from stdin.
    3. At the 5-turn checkpoint, print the summary and ask for confirmation.
    4. On COMPLETE, render a PDF if ``output_pdf`` is provided.

    Args:
        raw_history: Raw career history text (may be multi-line).
        output_pdf: Optional path to write the final PDF resume.
        session_id: Optional caller-supplied session ID.
        use_firestore: If ``True``, use Firestore for session persistence.
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
    print("=" * 60)

    # ── Start: ingest + opening question ─────────────────────────────────────
    question = asyncio.run(session.start(raw_history))

    while True:
        if not question:
            # Session ended or no question surfaced — check phase
            state = asyncio.run(session.current_state())
            if state.current_phase == PhaseStatus.COMPLETE:
                break
            # No question yet (e.g. ingest-only turn) — run another turn
            result = asyncio.run(session._read_turn_result())
            if result.is_complete:
                break
            question = result.next_question
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
            print(
                "\n[Upgrade required]: This task requires a paid Gemini model. "
                "Set DEV_GEMINI_KEY or provide your BYOK key to continue."
            )
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
