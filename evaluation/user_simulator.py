"""Adversarial vague-applicant simulator over the real discovery graph (Phase 3).

ADK 2.0.0 exposes no ``UserSimulator`` (see PROGRESS.md deviations), so this is
our own — deterministic and fixture-driven, driving the REAL ``DiscoverySession``
/ Runner (no graph bypass). It role-plays an applicant who answers vaguely until
pressed, then gives a metric-bearing answer, and records:

- the transcript (question → answer per turn),
- validated ``StarStory`` objects the grill loop committed,
- the ``question_count`` at which the 5-turn checkpoint brake fired,
- the **Pro-escalation rate** = fraction of grill turns that returned
  ``UpgradeRequired`` (a capability shortfall that would escalate to a paid model).

Determinism: the "agent" model is a scripted client whose metric extraction is
driven by the ACTUAL answer content (via ``workflows.nodes._contains_real_metric``),
so a vague answer is genuinely rejected and a specific one genuinely validated —
no live-model variance. The applicant's answers come from a fixture scenario.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import workflows.nodes as nodes
from cli.app import DiscoverySession
from config import AccessMode
from integration.model_client import GeminiModelClient
from schema import PhaseStatus, StarStory
from workflows.nodes import _contains_real_metric

_MAX_TURNS_DEFAULT = 30


# ── Scenario + result models ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Scenario:
    """A vague-applicant scenario (loaded from test_config.json)."""

    name: str
    raw_history: str
    entry_title: str
    entry_org: str
    reference_date: str
    vague_answers: list[str]
    specific_answer: str
    metric_after_turn: int  # give the specific (metric-bearing) answer on/after this grill turn

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Scenario:
        """Build a Scenario from a config dict (with sensible defaults)."""
        return Scenario(
            name=str(data["name"]),
            raw_history=str(data.get("raw_history", "Career history.")),
            entry_title=str(data.get("entry_title", "Engineer")),
            entry_org=str(data.get("entry_org", "Acme")),
            reference_date=str(data.get("reference_date", "2026-07-01")),
            vague_answers=[str(a) for a in data.get("vague_answers", ["we improved things a lot"])],
            specific_answer=str(
                data.get("specific_answer", "cut p99 from 800ms to 120ms across 40 services")
            ),
            metric_after_turn=int(data.get("metric_after_turn", 2)),
        )


@dataclass(frozen=True)
class SimulatedTurn:
    """One question→answer exchange in a simulation transcript."""

    question: str
    answer: str


@dataclass
class SimulationResult:
    """Outcome of a simulation run (for assertions + reporting).

    Determinism scope: the eval-relevant outputs are stable across repeated runs
    — the transcript, the number of validated stories and their ``result`` text,
    ``checkpoint_question_count``, ``grill_turns``, ``escalations``, and
    ``truncated``. The retained ``StarStory`` objects still carry incidental
    schema-level nondeterminism (``story_id`` via ``uuid4``, ``extracted_at`` via
    the clock); those fields are NOT normalized here and must not be used for
    cross-run equality.
    """

    scenario: str
    transcript: list[SimulatedTurn] = field(default_factory=list)
    validated_stories: list[StarStory] = field(default_factory=list)
    checkpoint_question_count: int | None = None  # question_count when the brake fired
    grill_turns: int = 0
    escalations: int = 0
    truncated: bool = False  # True if the run hit max_turns without completing/escalating

    @property
    def pro_escalation_rate(self) -> float:
        """Fraction of grill turns that returned UpgradeRequired (escalation)."""
        return self.escalations / self.grill_turns if self.grill_turns else 0.0

    @property
    def checkpoint_fired(self) -> bool:
        """True if the 5-turn checkpoint brake fired during the run."""
        return self.checkpoint_question_count is not None


# ── The simulated applicant ───────────────────────────────────────────────────


class VagueApplicant:
    """Answers vaguely until grill turn >= metric_after_turn, then gives a metric."""

    def __init__(self, scenario: Scenario) -> None:
        """Initialise from a scenario."""
        self._s = scenario

    def answer(self, question: str, grill_turn: int) -> str:
        """Return the applicant's answer for a given grill turn (1-based)."""
        if grill_turn >= self._s.metric_after_turn:
            return self._s.specific_answer
        idx = (grill_turn - 1) % len(self._s.vague_answers)
        return self._s.vague_answers[idx]


# ── The scripted "agent" model (deterministic, content-driven) ────────────────


class _ScriptedAgentClient:
    """A deterministic model client for the AGENT side of the loop.

    Metric extraction is driven by the actual answer content, so the grill loop's
    accept/reject behavior is genuine — not hard-coded per turn.
    """

    def __init__(self, scenario: Scenario) -> None:
        """Initialise from a scenario (for the seeded ingest timeline)."""
        self._s = scenario

    def generate(self, model_id: str, system: str, user: str) -> str:
        """Return a scripted response keyed by the system-prompt role."""
        if "analyzing a career history" in system:  # INGEST
            return json.dumps(
                {
                    "timeline": [
                        {
                            "type": "full_time",
                            "title": self._s.entry_title,
                            "org": self._s.entry_org,
                            "start_date": "2023",
                            "end_date": "2024",
                            "bullets": [],
                        }
                    ],
                    "summary": "Simulated candidate.",
                }
            )
        if "data extraction assistant" in system:  # METRIC_EXTRACTION
            answer = user.split("User's answer:")[-1].strip()
            found = _contains_real_metric(answer)
            return json.dumps(
                {
                    "situation": "Context.",
                    "task": "Task.",
                    "action": "Action.",
                    "result": answer,
                    "metrics_found": found,
                    "metric_summary": answer if found else "",
                }
            )
        if "senior engineering colleague" in system:  # GRILL question
            return "Can you put a concrete number on that impact?"
        if "summarizing progress" in system:  # CHECKPOINT summary
            return "Here's what we've captured so far. Does this look right?"
        if "assembling a master resume" in system:  # FINALIZE
            return json.dumps({"summary": "Simulated professional summary."})
        return "{}"


# ── Runner ────────────────────────────────────────────────────────────────────


async def _simulate_async(scenario: Scenario, *, max_turns: int) -> SimulationResult:
    """Drive one simulation through the real DiscoverySession/Runner."""
    from google.adk.sessions import BaseSessionService, InMemorySessionService

    svc = cast("BaseSessionService", InMemorySessionService())  # type: ignore[no-untyped-call]
    agent = cast(GeminiModelClient, _ScriptedAgentClient(scenario))
    session = DiscoverySession(
        user_id="sim-user",
        access_mode=AccessMode.FREE,
        model_client=agent,
        session_service=svc,
    )
    applicant = VagueApplicant(scenario)
    result = SimulationResult(scenario=scenario.name)

    question = await session.start(scenario.raw_history, reference_date=scenario.reference_date)

    for _ in range(max_turns):
        state = await session.current_state()
        if state.current_phase == PhaseStatus.COMPLETE:
            break
        if state.current_phase == PhaseStatus.CHECKPOINT and state.checkpoint_delta_summary:
            if result.checkpoint_question_count is None:
                result.checkpoint_question_count = state.question_count
            question = await session.confirm_checkpoint()
            continue
        if not question:
            turn = await session.advance()
            if turn.upgrade_required:
                # A capability shortfall can surface on the opening grill (before
                # any answer) — count it as an escalated grill turn.
                result.escalations += 1
                result.grill_turns += 1
                break
            if turn.is_complete:
                break
            question = turn.next_question
            continue
        answer = applicant.answer(question, result.grill_turns + 1)
        result.transcript.append(SimulatedTurn(question=question, answer=answer))
        turn = await session.answer(answer)
        result.grill_turns += 1
        if turn.upgrade_required:
            result.escalations += 1
            break  # cannot proceed without escalating to a paid model
        question = turn.next_question
    else:
        # Loop exhausted max_turns without a natural break (complete/escalate) —
        # surface it so callers don't misread an incomplete run as "no results".
        result.truncated = True
        print(
            f"[user_simulator] scenario '{scenario.name}' hit max_turns={max_turns} "
            "without completing.",
            file=sys.stderr,
        )

    final = await session.current_state()
    result.validated_stories = [
        s for s in final.extracted_star_stories if s.metrics_validated
    ]
    return result


def run_simulation(scenario: Scenario, *, max_turns: int = _MAX_TURNS_DEFAULT) -> SimulationResult:
    """Run a scenario to completion (or max_turns), restoring global client state.

    Drives the REAL discovery graph via ``DiscoverySession``. Deterministic:
    the agent model is scripted and content-driven; the applicant is fixture-driven.

    Args:
        scenario: The vague-applicant scenario.
        max_turns: Safety cap on turns.

    Returns:
        A :class:`SimulationResult`.
    """
    original_factory = nodes._client_factory
    try:
        return asyncio.run(_simulate_async(scenario, max_turns=max_turns))
    finally:
        # DiscoverySession installs a global node client factory — restore it.
        nodes.set_model_client_factory(original_factory)


def load_scenarios(path: Path) -> list[Scenario]:
    """Load scenarios from a JSON config (a top-level ``{"scenarios": [...]}``)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Scenario.from_dict(s) for s in data["scenarios"]]


def _format_report(results: list[SimulationResult]) -> str:
    """Render a plain-text evaluation report."""
    lines = ["CareerEngine — evaluation report", "=" * 40]
    for r in results:
        lines.append(
            f"[{r.scenario}] grills={r.grill_turns} validated={len(r.validated_stories)} "
            f"checkpoint@qc={r.checkpoint_question_count} "
            f"pro_escalation_rate={r.pro_escalation_rate:.2f} "
            f"truncated={r.truncated}"
        )
    return "\n".join(lines)


def main() -> None:
    """Run all bundled scenarios and print the evaluation report."""
    config = Path(__file__).parent / "test_config.json"
    results = [run_simulation(s) for s in load_scenarios(config)]
    print(_format_report(results))


if __name__ == "__main__":
    main()
