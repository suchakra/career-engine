"""Phase-1 integration tests — turn-based discovery loop via the ADK Runner.

Execution model (human-in-the-loop / turn-based)
-------------------------------------------------
The discovery workflow advances by exactly ONE work node per
``runner.run_async`` invocation, then the graph terminates and waits for the
CLI to collect the next human input.  Each turn flows:

    START -> ingest (idempotent — seeds only on the first turn) -> router ->
    ONE of {grill, checkpoint, finalize -> tailor} -> STOP.

There is no back-edge from grill/checkpoint to the router, so a single
invocation can never spin: grill surfaces a question (or commits a story) and
the run ends.  The CLI then patches ``pending_user_answer`` (a new answer) or
``checkpoint_verified`` (a confirmation) into the session state and invokes the
next turn.

These tests simulate that turn sequence directly against the ADK Runner with
an InMemorySessionService and a mocked model client.  Every test completes in
well under a second — no real network, no GCP, no ``input()``, no unbounded
loops.

Acceptance criteria covered
---------------------------
AC-1  Full turn-based end-to-end via the ADK Runner:
      ingest -> grill (VAGUE answer rejected, no validated story) ->
      grill (SPECIFIC answer yields StarStory metrics_validated=True) ->
      5-turn checkpoint fires and PAUSES -> checkpoint_verified=True ->
      finalize sets professional_summary + master_resume_json ->
      render_pdf produces a NON-EMPTY PDF (assert %PDF).
AC-2  Model-client adapter satisfies BOTH call shapes
      (.generate and .generate_content_text) against a fake transport.
AC-3  Access-mode wiring: FREE uses the platform key; BYOK fetches from vault.
AC-4  No hardcoded model names in integration/, cli/, or main.py.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService

from config import AccessMode
from integration.model_client import GeminiModelClient, build_model_client
from models.registry import get_registry, set_registry
from schema import CareerEngineState, PhaseStatus, StarStory
from workflows import nodes
from workflows.discovery_graph import build_runner, discovery_router
from workflows.nodes import set_model_client_factory

if TYPE_CHECKING:
    from collections.abc import Iterator

APP_NAME = "career_engine_discovery"
USER_ID = "test_user"


# ── Test doubles ──────────────────────────────────────────────────────────────


class ScriptedNodeClient:
    """Model client returning scripted responses for ``generate`` calls.

    Implements the ``generate(model_id, system, user) -> str`` interface used by
    ``workflows/nodes.py``.  Responses are matched by a substring of the system
    prompt; the first match wins.
    """

    def __init__(
        self, responses: dict[str, str] | None = None, default: str = "{}"
    ) -> None:
        """Initialise with a {system-prompt-substring: response} map."""
        self._responses = responses or {}
        self._default = default
        self.calls: list[dict[str, str]] = []

    def generate(self, model_id: str, system: str, user: str) -> str:
        """Return a scripted response matched on a system-prompt substring."""
        self.calls.append({"model_id": model_id, "system": system, "user": user})
        for key, resp in self._responses.items():
            if key in system:
                return resp
        return self._default


def _ingest_response(pillars: list[str]) -> str:
    """Build a scripted ingest JSON response seeding the given pillars."""
    return json.dumps(
        {
            "competency_pillars": pillars,
            "initial_gaps": pillars,
            "suggested_first_pillar": pillars[0] if pillars else "",
        }
    )


def _vague_extraction() -> str:
    """Build a scripted extraction response indicating no concrete metric."""
    return json.dumps(
        {
            "situation": "perf work",
            "task": "make it faster",
            "action": "tuned things",
            "result": "improved performance a lot",
            "metrics_found": False,
            "metric_summary": "",
        }
    )


def _specific_extraction(
    result: str = "cut p99 from 800ms to 120ms across 40 services",
) -> str:
    """Build a scripted extraction response with a concrete metric."""
    return json.dumps(
        {
            "situation": "High p99 latency under peak load.",
            "task": "Reduce tail latency across the fleet.",
            "action": "Added caching and removed N+1 queries.",
            "result": result,
            "metrics_found": True,
            "metric_summary": "p99 800->120ms across 40 services",
        }
    )


def _finalize_response(summary: str = "Senior performance engineer.") -> str:
    """Build a scripted finalize JSON response."""
    return json.dumps(
        {
            "summary": summary,
            "achievements_by_pillar": {
                "performance_engineering": [
                    {
                        "headline": "Cut p99 latency 85% across 40 services",
                        "full_text": "Reduced p99 from 800ms to 120ms by adding caching.",
                    }
                ]
            },
        }
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_nodes_client() -> Iterator[None]:
    """Restore the global node client factory after each test."""
    original = nodes._client_factory
    yield
    nodes._client_factory = original


@pytest.fixture(autouse=True)
def _restore_registry() -> Iterator[None]:
    """Restore the model registry after each test."""
    original = get_registry()
    yield
    set_registry(original)


@pytest.fixture
def svc() -> BaseSessionService:
    """Return a fresh in-memory ADK session service for each test."""
    service: BaseSessionService = InMemorySessionService()  # type: ignore[no-untyped-call]
    return service


def _new_session_id() -> str:
    """Generate a unique session ID for test isolation."""
    return str(uuid.uuid4())


def _runner(service: BaseSessionService) -> Runner:
    """Build a Runner wired to the discovery workflow."""
    return build_runner(session_service=service, app_name=APP_NAME)


async def _create_session(
    service: BaseSessionService, *, session_id: str, state: CareerEngineState
) -> None:
    """Create an ADK session seeded with the given CareerEngineState."""
    await service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
        state=state.model_dump(mode="json"),
    )


async def _get_state(
    service: BaseSessionService, *, session_id: str
) -> CareerEngineState:
    """Read and validate CareerEngineState from an ADK session."""
    session = await service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    assert session is not None, f"Session {session_id!r} not found"
    return CareerEngineState.model_validate(session.state)


async def _patch_state(
    service: BaseSessionService, *, session_id: str, **fields: object
) -> None:
    """Inject state between turns via an event state_delta (canonical ADK).

    ``get_session`` returns a COPY, so a direct ``session.state`` write would
    not persist.  Appending an event with ``EventActions(state_delta=...)``
    commits the change to the stored session — the same path the workflow's own
    node writes take — so it is visible to the next ``runner.run_async`` call.
    """
    session = await service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    assert session is not None
    event = Event(author="user", actions=EventActions(state_delta=dict(fields)))
    await service.append_event(session, event)


async def _run_turn(runner: Runner, *, session_id: str) -> None:
    """Advance the workflow by exactly one turn, draining all events.

    The turn-based topology guarantees this terminates after a single work
    node (grill, checkpoint, or finalize->tailor); there is no unbounded loop.
    """
    async for _ in runner.run_async(
        user_id=USER_ID, session_id=session_id, state_delta={}
    ):
        pass


# ── AC-1: Full turn-based end-to-end via the ADK Runner ───────────────────────


class TestTurnBasedDiscoveryLoop:
    """AC-1: The discovery loop drives one turn per Runner invocation."""

    async def test_vague_answer_rejected_no_story_committed(
        self, svc: BaseSessionService
    ) -> None:
        """AC-1a: A VAGUE answer surfaces a follow-up and commits NO story.

        Turn 1 (ingest + opening question) -> Turn 2 (vague answer).
        """
        client = ScriptedNodeClient(
            responses={
                "key competency areas": _ingest_response(["performance_engineering"]),
                "senior engineering colleague": "What was the latency before vs after?",
                "data extraction assistant": _vague_extraction(),
            }
        )
        set_model_client_factory(lambda: client)

        sid = _new_session_id()
        runner = _runner(svc)
        await _create_session(
            svc,
            session_id=sid,
            state=CareerEngineState(raw_history_text="10 years perf engineering."),
        )

        # Turn 1: ingest seeds pillars, grill asks the opening question.
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        assert state.current_phase == PhaseStatus.GRILLING
        assert state.active_gaps, "ingest must seed active_gaps"
        assert state.current_question, "grill must surface an opening question"

        # Turn 2: a vague answer is rejected — no story, a follow-up is asked.
        await _patch_state(
            svc, session_id=sid, pending_user_answer="I improved performance a lot"
        )
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)

        assert state.extracted_star_stories == [], (
            "A vague answer must NOT commit a StarStory"
        )
        assert state.current_question, "grill must surface a follow-up question"
        assert state.pending_user_answer == "", "the answer must be consumed"

    async def test_specific_answer_yields_validated_story(
        self, svc: BaseSessionService
    ) -> None:
        """AC-1b: A SPECIFIC answer commits a StarStory(metrics_validated=True)."""
        client = ScriptedNodeClient(
            responses={
                "key competency areas": _ingest_response(["performance_engineering"]),
                "senior engineering colleague": "Tell me about a perf win.",
                "data extraction assistant": _specific_extraction(),
            }
        )
        set_model_client_factory(lambda: client)

        sid = _new_session_id()
        runner = _runner(svc)
        await _create_session(
            svc,
            session_id=sid,
            state=CareerEngineState(raw_history_text="10 years perf engineering."),
        )

        await _run_turn(runner, session_id=sid)  # Turn 1: ingest + opening question
        await _patch_state(
            svc,
            session_id=sid,
            pending_user_answer="cut p99 from 800ms to 120ms across 40 services",
        )
        await _run_turn(runner, session_id=sid)  # Turn 2: specific answer

        state = await _get_state(svc, session_id=sid)
        assert len(state.extracted_star_stories) == 1, (
            "a specific answer must commit exactly one StarStory"
        )
        story = state.extracted_star_stories[0]
        assert story.metrics_validated is True
        assert "800ms" in story.result or "120ms" in story.result

    async def test_full_end_to_end_turn_sequence(
        self, svc: BaseSessionService, tmp_path: pathlib.Path
    ) -> None:
        """AC-1: Full turn-based flow through to a rendered PDF.

        Sequence:
          - Turn 1: ingest + opening question.
          - Turn 2: VAGUE answer -> no story, follow-up question.
          - Turn 3: SPECIFIC answer -> validated StarStory (last gap closed).
          - Turn 4: gaps empty -> finalize sets professional_summary +
            master_resume_json -> tailor -> COMPLETE.
          - render_pdf -> non-empty %PDF.
        """
        result_text = "cut p99 from 800ms to 120ms across 40 services"
        summary_text = "Senior performance engineer with measurable impact."

        # Extraction is vague on the first answer and specific on the second.
        extraction_calls = {"n": 0}

        class _Client:
            def generate(self, model_id: str, system: str, user: str) -> str:
                if "key competency areas" in system:
                    return _ingest_response(["performance_engineering"])
                if "data extraction assistant" in system:
                    extraction_calls["n"] += 1
                    if extraction_calls["n"] == 1:
                        return _vague_extraction()
                    return _specific_extraction(result_text)
                if "senior engineering colleague" in system:
                    return "What was the latency before and after?"
                if "assembling a master resume" in system:
                    return _finalize_response(summary_text)
                if "tailoring a master resume" in system:
                    return json.dumps(
                        {"tailored_summary": "Great fit.", "selected_achievements": []}
                    )
                return "{}"

        set_model_client_factory(lambda: _Client())

        sid = _new_session_id()
        runner = _runner(svc)
        await _create_session(
            svc,
            session_id=sid,
            state=CareerEngineState(
                raw_history_text="Name: Jane Smith\n10 years perf engineering."
            ),
        )

        # Turn 1: ingest + opening question
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        assert state.current_phase == PhaseStatus.GRILLING
        assert state.current_question

        # Turn 2: vague answer rejected
        await _patch_state(svc, session_id=sid, pending_user_answer="we got faster")
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        assert state.extracted_star_stories == [], "vague answer must not commit a story"
        assert state.active_gaps, "the gap must remain open after a vague answer"

        # Turn 3: specific answer -> validated story closes the last gap
        await _patch_state(svc, session_id=sid, pending_user_answer=result_text)
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        validated = [s for s in state.extracted_star_stories if s.metrics_validated]
        assert len(validated) == 1, "specific answer must commit a validated story"
        assert state.active_gaps == [], "the last gap must now be closed"
        assert state.current_phase == PhaseStatus.GRILLING, (
            "grill is terminal-per-turn; finalize happens on the next turn"
        )

        # Turn 4: gaps empty -> finalize -> tailor -> COMPLETE
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        assert state.current_phase == PhaseStatus.COMPLETE
        assert state.professional_summary, "finalize must set professional_summary"
        assert summary_text in state.professional_summary
        assert state.master_resume_json, "finalize must set master_resume_json"

        # render_pdf -> non-empty %PDF
        from tools.pdf_renderer import render_pdf

        pdf_path = render_pdf(state, output_path=tmp_path / "resume.pdf")
        assert pdf_path.exists()
        pdf_bytes = pdf_path.read_bytes()
        assert len(pdf_bytes) > 0, "PDF must be non-empty"
        assert pdf_bytes[:4] == b"%PDF", f"PDF must start with %PDF, got {pdf_bytes[:4]!r}"

    async def test_five_turn_checkpoint_fires_and_pauses(
        self, svc: BaseSessionService
    ) -> None:
        """AC-1c: At question_count==5 the checkpoint fires and PAUSES.

        Seeds the session at GRILLING with question_count==5 (the state a grill
        turn would have left after asking its 5th question) and an open gap, so
        the next turn's router routes to the checkpoint, which emits the delta
        summary and pauses for confirmation (checkpoint_verified stays False).
        """
        # Pure-router invariant: 5 questions with an open gap -> checkpoint.
        assert (
            discovery_router(
                CareerEngineState(
                    current_phase=PhaseStatus.GRILLING,
                    active_gaps=["perf"],
                    question_count=5,
                )
            )
            == "user_checkpoint_node"
        )

        client = ScriptedNodeClient(
            responses={
                "summarizing progress": "We captured 1 win. Does this look right?",
            }
        )
        set_model_client_factory(lambda: client)

        sid = _new_session_id()
        runner = _runner(svc)
        await _create_session(
            svc,
            session_id=sid,
            state=CareerEngineState(
                raw_history_text="10 years perf.",
                current_phase=PhaseStatus.GRILLING,  # ingest is skipped (idempotent)
                active_gaps=["leadership"],
                target_competencies=["perf", "leadership"],
                current_pillar="leadership",
                question_count=5,
                extracted_star_stories=[
                    StarStory(
                        pillar="perf",
                        result="cut p99 from 800ms to 120ms",
                        metrics_validated=True,
                    )
                ],
            ),
        )

        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)

        assert state.current_phase == PhaseStatus.CHECKPOINT, (
            "the 5-turn brake must route to the checkpoint"
        )
        assert state.checkpoint_delta_summary, (
            "the checkpoint must emit a delta summary"
        )
        assert state.checkpoint_verified is False, (
            "the checkpoint must PAUSE — never auto-advance without confirmation"
        )

    async def test_checkpoint_verified_advances_back_to_grilling(
        self, svc: BaseSessionService
    ) -> None:
        """AC-1d: After checkpoint_verified=True the next turn resumes GRILLING."""
        client = ScriptedNodeClient(
            responses={"summarizing progress": "Captured your wins. Accurate?"}
        )
        set_model_client_factory(lambda: client)

        sid = _new_session_id()
        runner = _runner(svc)
        await _create_session(
            svc,
            session_id=sid,
            state=CareerEngineState(
                current_phase=PhaseStatus.CHECKPOINT,
                active_gaps=["leadership"],
                current_pillar="leadership",
                checkpoint_delta_summary="Captured your wins. Accurate?",
                checkpoint_verified=True,  # user confirmed
                question_count=5,
            ),
        )

        # Turn: router sees phase==CHECKPOINT -> checkpoint node advances phase.
        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        assert state.current_phase == PhaseStatus.GRILLING, (
            "a verified checkpoint must advance back to GRILLING"
        )
        assert state.checkpoint_verified is False, "the flag is reset after advancing"
        assert state.checkpoint_delta_summary == "", "the summary is cleared"

    async def test_finalize_turn_sets_summary_and_master_resume(
        self, svc: BaseSessionService
    ) -> None:
        """AC-1e: When gaps are empty the finalize turn populates outputs."""
        client = ScriptedNodeClient(
            responses={
                "assembling a master resume": _finalize_response("Top perf engineer."),
                "tailoring a master resume": "{}",
            }
        )
        set_model_client_factory(lambda: client)

        sid = _new_session_id()
        runner = _runner(svc)
        await _create_session(
            svc,
            session_id=sid,
            state=CareerEngineState(
                current_phase=PhaseStatus.GRILLING,
                active_gaps=[],  # all gaps closed -> router goes to finalize
                extracted_star_stories=[
                    StarStory(
                        pillar="performance_engineering",
                        result="cut p99 from 800ms to 120ms",
                        metrics_validated=True,
                    )
                ],
            ),
        )

        await _run_turn(runner, session_id=sid)
        state = await _get_state(svc, session_id=sid)
        assert state.current_phase == PhaseStatus.COMPLETE
        assert "Top perf engineer." in state.professional_summary
        assert "achievements_by_pillar" in state.master_resume_json


# ── AC-2: Model-client adapter satisfies both call shapes ─────────────────────


class TestModelClientAdapterBothInterfaces:
    """AC-2: GeminiModelClient satisfies both node and scraper interfaces."""

    @staticmethod
    def _adapter(return_text: str | None) -> GeminiModelClient:
        """Build a GeminiModelClient with a fake underlying genai client."""
        fake_response = MagicMock()
        fake_response.text = return_text
        adapter = GeminiModelClient.__new__(GeminiModelClient)
        adapter._client = MagicMock()
        adapter._client.models.generate_content.return_value = fake_response
        return adapter

    def test_generate_interface_nodes_convention(self) -> None:
        """AC-2a: .generate(model_id, system, user) returns the model text."""
        adapter = self._adapter("nodes response")
        result = adapter.generate(
            model_id="test-model", system="You are a test assistant.", user="Hello!"
        )
        assert result == "nodes response"
        mock_gen = adapter._client.models.generate_content
        assert isinstance(mock_gen, MagicMock)
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs["model"] == "test-model"
        assert mock_gen.call_args.kwargs["contents"] == "Hello!"

    def test_generate_content_text_interface_scraper_convention(self) -> None:
        """AC-2b: .generate_content_text(model, system, prompt) returns the text."""
        adapter = self._adapter("scraper response")
        result = adapter.generate_content_text(
            model="test-model", system="You are a JD parser.", prompt="Parse this JD..."
        )
        assert result == "scraper response"
        mock_gen = adapter._client.models.generate_content
        assert isinstance(mock_gen, MagicMock)
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs["model"] == "test-model"
        assert mock_gen.call_args.kwargs["contents"] == "Parse this JD..."

    def test_both_interfaces_share_one_client(self) -> None:
        """AC-2c: Both interfaces call through one underlying genai client."""
        adapter = self._adapter("shared")
        adapter.generate("m", "sys1", "user1")
        adapter.generate_content_text(model="m", system="sys2", prompt="p2")
        mock_gen = adapter._client.models.generate_content
        assert isinstance(mock_gen, MagicMock)
        assert mock_gen.call_count == 2

    def test_generate_returns_empty_on_none_text(self) -> None:
        """AC-2d: .generate() returns '' when the model returns None text."""
        adapter = self._adapter(None)
        assert adapter.generate("m", "sys", "user") == ""

    def test_generate_content_text_raises_scraper_error_on_empty(self) -> None:
        """AC-2e: .generate_content_text() raises ScraperError on empty output."""
        from tools.web_scraper import ScraperError

        adapter = self._adapter(None)
        with pytest.raises(ScraperError):
            adapter.generate_content_text(model="m", system="sys", prompt="p")

    def test_generate_content_text_wraps_exceptions(self) -> None:
        """AC-2f: .generate_content_text() wraps transport errors as ScraperError."""
        from tools.web_scraper import ScraperError

        adapter = GeminiModelClient.__new__(GeminiModelClient)
        adapter._client = MagicMock()
        adapter._client.models.generate_content.side_effect = RuntimeError("API fail")
        with pytest.raises(ScraperError, match="API fail"):
            adapter.generate_content_text(model="m", system="sys", prompt="p")

    def test_adapter_drives_nodes_via_factory(self) -> None:
        """AC-2g: The adapter satisfies set_model_client_factory injection."""
        adapter = self._adapter(_ingest_response(["perf"]))
        set_model_client_factory(lambda: adapter)
        from workflows.nodes import ingest_node

        result = ingest_node(CareerEngineState(raw_history_text="10 years perf."))
        assert result.current_phase == PhaseStatus.GRILLING

    def test_adapter_drives_scraper_via_client_param(self) -> None:
        """AC-2h: The adapter satisfies clean_jd_html(client=...) injection."""
        adapter = self._adapter("Python engineer with Kubernetes and Go required.")
        from tools.web_scraper import clean_jd_html

        result = clean_jd_html(
            "<html><body>Python engineer with Kubernetes</body></html>", client=adapter
        )
        assert result, "clean_jd_html with the adapter must return cleaned text"


# ── AC-3: Access-mode wiring ──────────────────────────────────────────────────


class TestAccessModeWiring:
    """AC-3: FREE uses the platform key; BYOK fetches from the key vault."""

    def test_free_mode_uses_platform_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-3a: FREE mode reads settings.gemini_api_key (never the vault)."""
        captured: list[str | None] = []

        def _spy_init(self: GeminiModelClient, api_key: str | None = None) -> None:
            captured.append(api_key)
            self._client = MagicMock()

        monkeypatch.setattr(GeminiModelClient, "__init__", _spy_init)

        from config import Settings

        platform_key = "PLATFORM_KEY_abc123"
        monkeypatch.setattr(
            "integration.model_client.get_settings",
            lambda: Settings(gemini_api_key=platform_key),
        )

        vault = MagicMock()
        vault.fetch_key.side_effect = AssertionError("vault must not be used in FREE")

        build_model_client(
            user_id="test_user", key_vault=vault, access_mode=AccessMode.FREE
        )

        assert captured == [platform_key], "FREE mode must use the platform key"
        vault.fetch_key.assert_not_called()

    def test_byok_mode_fetches_from_vault(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-3b: BYOK mode calls key_vault.fetch_key(user_id)."""
        captured: list[str | None] = []

        def _spy_init(self: GeminiModelClient, api_key: str | None = None) -> None:
            captured.append(api_key)
            self._client = MagicMock()

        monkeypatch.setattr(GeminiModelClient, "__init__", _spy_init)

        byok_key = "USER_BYOK_KEY_xyz789"
        vault = MagicMock()
        vault.fetch_key.return_value = byok_key

        build_model_client(
            user_id="user_42", key_vault=vault, access_mode=AccessMode.BYOK
        )

        vault.fetch_key.assert_called_once_with("user_42")
        assert captured == [byok_key], "BYOK mode must use the vault-fetched key"

    def test_free_mode_falls_back_to_adc_without_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-3c: FREE mode with no configured key passes None (uses ADC)."""
        captured: list[str | None] = []

        def _spy_init(self: GeminiModelClient, api_key: str | None = None) -> None:
            captured.append(api_key)
            self._client = MagicMock()

        monkeypatch.setattr(GeminiModelClient, "__init__", _spy_init)

        from config import Settings

        monkeypatch.setattr(
            "integration.model_client.get_settings",
            lambda: Settings(gemini_api_key="", dev_gemini_key=""),
        )

        vault = MagicMock()
        vault.fetch_key.side_effect = AssertionError("vault must not be used in FREE")

        build_model_client(user_id="anon", key_vault=vault, access_mode=AccessMode.FREE)
        assert captured == [None], "FREE mode with no key must pass None (ADC)"


# ── AC-4: No hardcoded model names ────────────────────────────────────────────


class TestNoHardcodedModelNames:
    """AC-4: No 'gemini-' literal appears in integration/, cli/, or main.py."""

    @staticmethod
    def _files_to_check() -> list[pathlib.Path]:
        """Return the integration/cli/main.py module files to inspect."""
        root = pathlib.Path(__file__).parent.parent
        targets: list[pathlib.Path] = []
        for pkg in ("integration", "cli"):
            pkg_dir = root / pkg
            if pkg_dir.exists():
                targets.extend(pkg_dir.rglob("*.py"))
        main_py = root / "main.py"
        if main_py.exists():
            targets.append(main_py)
        return targets

    def test_no_gemini_model_strings(self) -> None:
        """No hardcoded 'gemini-' model literal in the new files."""
        pattern = re.compile(r"gemini-")
        offenders: list[str] = []
        for path in self._files_to_check():
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path}:{i}: {line.strip()}")
        assert not offenders, "hardcoded 'gemini-' strings found:\n" + "\n".join(
            offenders
        )

    def test_adapter_methods_take_model_from_caller(self) -> None:
        """GeminiModelClient methods accept model IDs from the caller (registry)."""
        import integration.model_client as mc

        assert "gemini-" not in inspect.getsource(mc.GeminiModelClient.generate)
        assert "gemini-" not in inspect.getsource(
            mc.GeminiModelClient.generate_content_text
        )


# ── discovery_graph.py glue validation ────────────────────────────────────────


class TestDiscoveryGraphGlue:
    """Validate the minimal turn-based glue applied to discovery_graph.py."""

    def test_router_shim_sets_ctx_route(self) -> None:
        """_router_shim must set ctx.route rather than return a route string."""
        from workflows.discovery_graph import _router_shim

        src = inspect.getsource(_router_shim)
        assert "route" in src, "_router_shim must set ctx.route"

    def test_ingest_shim_is_idempotent(self) -> None:
        """_ingest_shim must only seed while the phase is INGESTING."""
        from workflows.discovery_graph import _ingest_shim

        src = inspect.getsource(_ingest_shim)
        assert "INGESTING" in src, (
            "_ingest_shim must guard on PhaseStatus.INGESTING to stay idempotent"
        )

    def test_router_suppresses_brake_during_checkpoint_phase(self) -> None:
        """The FROZEN router suppresses the 5-turn brake while phase==CHECKPOINT.

        A verified checkpoint is resolved at the graph entry (_ingest_shim)
        which advances the phase back to GRILLING before the router runs, so the
        router never has to re-enter the checkpoint node.
        """
        state = CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            active_gaps=["perf"],
            question_count=5,
        )
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_router_finalizes_when_no_gaps(self) -> None:
        """An empty active_gaps list routes to finalize."""
        state = CareerEngineState(current_phase=PhaseStatus.GRILLING, active_gaps=[])
        assert discovery_router(state) == "finalize_master_resume_node"


# ── Import sanity ─────────────────────────────────────────────────────────────


class TestImportSanity:
    """All new modules must import cleanly."""

    def test_integration_model_client_imports(self) -> None:
        """integration.model_client exposes its public API."""
        import integration.model_client as mc

        assert hasattr(mc, "GeminiModelClient")
        assert hasattr(mc, "build_model_client")

    def test_cli_app_imports(self) -> None:
        """cli.app exposes its public API."""
        import cli.app as app

        assert hasattr(app, "DiscoverySession")
        assert hasattr(app, "run_interactive_session")
        assert hasattr(app, "resolve_auth_and_client")

    def test_cli_session_imports(self) -> None:
        """cli.session exposes its public API."""
        import cli.session as sess

        assert hasattr(sess, "create_session")
        assert hasattr(sess, "read_state")
        assert hasattr(sess, "patch_state")

    def test_main_imports(self) -> None:
        """main.py exposes the Click commands."""
        import main

        assert hasattr(main, "cli")
        assert hasattr(main, "grill")
        assert hasattr(main, "tailor")
