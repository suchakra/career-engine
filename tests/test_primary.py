"""Unit tests for discovery/primary.py — the Evaluator/Orchestrator agent.

Covers the deterministic hard-reject gate, the heuristic + model evaluators,
the pure evaluate_batch → EvaluationDiff, and the bounded A2A discovery loop.
No network and no keys: the Scout is fed canned batches and the model client is
a typed stub.
"""

from __future__ import annotations

from typing import Any, cast

from discovery.primary import (
    DiscoveryResult,
    HeuristicEvaluator,
    ModelEvaluator,
    PrimaryAgent,
    _parse_classification,
    evaluate_batch,
    hard_reject_reason,
)
from discovery.scout import Scout
from integration.model_client import GeminiModelClient, ModelAPIError
from schema import (
    EmploymentType,
    EvaluationDiff,
    InteractionLedger,
    JobMetadata,
    JobOpportunity,
    MatchStatus,
    ScoutBatchStatus,
    ScoutDirective,
    SessionPreferences,
    make_job_id,
)


def _job(ext: str, *, title: str = "Engineer", company: str = "Acme", desc: str = "") -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", ext),
        metadata=JobMetadata(title=title, company=company, employment_type=EmploymentType.CONTRACT),
        raw_description=desc,
    )


_PREFS = SessionPreferences(
    target_roles=["Fractional CTO"],
    nice_to_haves=["AWS", "MCP"],
    dealbreakers=["rigid 100% on-site", "pure maintenance"],
)


# ── Hard-reject gate ──────────────────────────────────────────────────────────


class TestHardRejectGate:
    def test_already_applied_is_hard_rejected(self) -> None:
        job = _job("1")
        ledger = InteractionLedger(already_applied_ids=[job.job_id])
        assert hard_reject_reason(job, _PREFS, ledger) is not None

    def test_rejected_company_is_hard_rejected(self) -> None:
        job = _job("2", company="Legacy Corp")
        ledger = InteractionLedger(rejected_companies=["legacy corp"])
        assert hard_reject_reason(job, _PREFS, ledger) is not None

    def test_dealbreaker_keyword_is_hard_rejected(self) -> None:
        job = _job("3", desc="This role is on-site five days a week.")
        assert hard_reject_reason(job, _PREFS, InteractionLedger()) is not None

    def test_clean_job_passes_gate(self) -> None:
        job = _job("4", title="Fractional CTO", desc="Remote AWS + MCP leadership.")
        assert hard_reject_reason(job, _PREFS, InteractionLedger()) is None


# ── Heuristic evaluator ───────────────────────────────────────────────────────


class TestHeuristicEvaluator:
    def test_accepts_on_priority_hit(self) -> None:
        result = HeuristicEvaluator().classify([_job("5", desc="Deep AWS + MCP work")], _PREFS)
        status, rationale = result[make_job_id("remotive", "5")]
        assert status is MatchStatus.ACCEPTED and "aws" in rationale.lower()

    def test_soft_rejects_without_hit(self) -> None:
        result = HeuristicEvaluator().classify([_job("6", title="Barista", desc="coffee")], _PREFS)
        assert result[make_job_id("remotive", "6")][0] is MatchStatus.SOFT_REJECT


# ── Pure evaluate_batch ───────────────────────────────────────────────────────


class TestEvaluateBatch:
    def _diff(self, jobs: list[JobOpportunity], *, remaining: int = 5) -> EvaluationDiff:
        return evaluate_batch(
            jobs,
            prefs=_PREFS,
            ledger=InteractionLedger(),
            evaluator=HeuristicEvaluator(),
            remaining=remaining,
            prev_directive=ScoutDirective(query="fractional cto"),
        )

    def test_hard_rejects_are_dropped_not_returned(self) -> None:
        jobs = [
            _job("a", desc="on-site only"),          # hard reject
            _job("b", desc="AWS platform"),          # accepted
        ]
        diff = self._diff(jobs)
        returned = {j.job_id for j in diff.accepted_jobs + diff.soft_rejected_jobs}
        assert make_job_id("remotive", "a") not in returned
        assert make_job_id("remotive", "b") in returned

    def test_returned_jobs_are_stamped(self) -> None:
        diff = self._diff([_job("c", desc="AWS + MCP")])
        assert diff.accepted_jobs[0].match_status is MatchStatus.ACCEPTED
        assert diff.accepted_jobs[0].ai_rationale
        assert diff.status is ScoutBatchStatus.APPROVE_BATCH

    def test_status_partial_accept_when_mixed(self) -> None:
        diff = self._diff([_job("d", desc="AWS"), _job("e", title="Barista", desc="coffee")])
        assert diff.status is ScoutBatchStatus.PARTIAL_ACCEPT

    def test_status_reject_batch_when_none_accepted(self) -> None:
        diff = self._diff([_job("f", title="Barista", desc="coffee")])
        assert diff.status is ScoutBatchStatus.REJECT_BATCH

    def test_next_directive_none_when_quota_met(self) -> None:
        diff = self._diff([_job("g", desc="AWS"), _job("h", desc="MCP")], remaining=2)
        assert diff.next_directive is None

    def test_next_directive_refines_when_quota_unmet(self) -> None:
        diff = self._diff([_job("i", title="Barista", company="CoffeeCo", desc="beans")], remaining=3)
        assert diff.next_directive is not None
        assert diff.next_directive.desired_count == 3  # still need 3


# ── Model evaluator ───────────────────────────────────────────────────────────


class _StubClient:
    def __init__(self, response: str | Exception) -> None:
        self._response = response

    def generate(self, model_id: str, system: str, user: str) -> str:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestModelEvaluator:
    def test_parses_model_json(self) -> None:
        jid = make_job_id("remotive", "j")
        payload = f'[{{"job_id": "{jid}", "status": "accepted", "rationale": "Great fit."}}]'
        ev = ModelEvaluator(cast(GeminiModelClient, _StubClient(payload)))
        result = ev.classify([_job("j")], _PREFS)
        assert result[jid] == (MatchStatus.ACCEPTED, "Great fit.")

    def test_falls_back_to_heuristic_on_bad_json(self) -> None:
        ev = ModelEvaluator(cast(GeminiModelClient, _StubClient("not json at all")))
        result = ev.classify([_job("k", desc="AWS")], _PREFS)
        assert result[make_job_id("remotive", "k")][0] is MatchStatus.ACCEPTED

    def test_falls_back_on_model_api_error(self) -> None:
        ev = ModelEvaluator(cast(GeminiModelClient, _StubClient(ModelAPIError("boom"))))
        result = ev.classify([_job("l", title="Barista", desc="coffee")], _PREFS)
        assert result[make_job_id("remotive", "l")][0] is MatchStatus.SOFT_REJECT

    def test_missing_job_defaults_to_soft_reject(self) -> None:
        ev = ModelEvaluator(cast(GeminiModelClient, _StubClient("[]")))
        result = ev.classify([_job("m", desc="AWS")], _PREFS)
        assert result[make_job_id("remotive", "m")][0] is MatchStatus.SOFT_REJECT

    def test_parse_ignores_unknown_ids(self) -> None:
        parsed = _parse_classification(
            '[{"job_id": "unknown", "status": "accepted", "rationale": "x"}]', {"real"}
        )
        assert parsed == {}


# ── Bounded discovery loop ────────────────────────────────────────────────────


class _ScriptedTools:
    """A JobToolClient returning a scripted batch per fetch; records directives."""

    def __init__(self, batches: list[list[JobOpportunity]]) -> None:
        self._batches = batches
        self.calls: list[ScoutDirective] = []

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        self.calls.append(directive)
        idx = min(len(self.calls) - 1, len(self._batches) - 1)
        return self._batches[idx]

    async def fetch_jd(self, url: str) -> str:
        return ""


def _primary(tools: _ScriptedTools, **kw: Any) -> PrimaryAgent:
    return PrimaryAgent(
        prefs=_PREFS, ledger=InteractionLedger(), scout=Scout(tools=tools), **kw
    )


async def test_loop_stops_at_desired_total() -> None:
    batch = [_job("n1", desc="AWS"), _job("n2", desc="MCP"), _job("n3", desc="AWS")]
    tools = _ScriptedTools([batch])
    result = await _primary(tools, desired_total=2, max_iterations=3).discover()
    assert len(result.accepted) >= 2
    assert result.iterations == 1  # first batch already satisfied the quota


async def test_loop_is_bounded_by_max_iterations() -> None:
    # Every batch is all soft-rejects → quota never met → must stop at the cap.
    soft_batch = [_job("s", title="Barista", company="CoffeeCo", desc="beans")]
    tools = _ScriptedTools([soft_batch, soft_batch, soft_batch, soft_batch])
    result = await _primary(tools, desired_total=5, max_iterations=3).discover()
    assert result.iterations == 3
    assert result.accepted == []


async def test_loop_dedupes_across_iterations() -> None:
    dup = [_job("d1", title="Barista", company="CoffeeCo", desc="beans")]
    tools = _ScriptedTools([dup, dup, dup])
    result = await _primary(tools, desired_total=5, max_iterations=3).discover()
    # The same job appears every iteration but must be counted at most once.
    assert len(result.soft_rejected) == 1


async def test_loop_refines_directive_between_iterations() -> None:
    b1 = [_job("r1", title="Barista", company="CoffeeCo", desc="beans")]
    b2 = [_job("r2", desc="AWS + MCP")]
    tools = _ScriptedTools([b1, b2])
    await _primary(tools, desired_total=5, max_iterations=3).discover()
    assert len(tools.calls) >= 2
    # The second directive should have folded in the rejected company exclusion.
    assert "CoffeeCo" in tools.calls[1].exclude_companies


async def test_result_is_a_discovery_result() -> None:
    tools = _ScriptedTools([[_job("x", desc="AWS")]])
    result = await _primary(tools, desired_total=1).discover()
    assert isinstance(result, DiscoveryResult) and result.accepted
