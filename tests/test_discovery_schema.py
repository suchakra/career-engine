"""Tests for the discovery (two-agent A2A) ontology — schema.py v2.5.0."""

from __future__ import annotations

from config import CONTRACT_VERSION
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
    WorkModel,
    make_job_id,
)


def _job(company: str = "Acme") -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", "123"),
        metadata=JobMetadata(
            title="Fractional CTO",
            company=company,
            work_model=WorkModel.REMOTE,
            employment_type=EmploymentType.FRACTIONAL,
            url="https://example.com/jobs/123",
        ),
        raw_description="Lead cloud + AI infra…",
        match_status=MatchStatus.ACCEPTED,
        ai_rationale="Accepted: fractional leadership + AWS/AI stack.",
    )


class TestRoundTrip:
    def test_job_opportunity_round_trips(self) -> None:
        job = _job()
        restored = JobOpportunity.model_validate_json(job.model_dump_json())
        assert restored == job
        assert restored.metadata.work_model is WorkModel.REMOTE
        assert restored.match_status is MatchStatus.ACCEPTED

    def test_evaluation_diff_round_trips_with_nested_jobs(self) -> None:
        diff = EvaluationDiff(
            status=ScoutBatchStatus.PARTIAL_ACCEPT,
            accepted_jobs=[_job("Acme")],
            soft_rejected_jobs=[_job("Globex")],
            next_directive=ScoutDirective(
                query="fractional cto", exclude_keywords=["director"], desired_count=5
            ),
        )
        restored = EvaluationDiff.model_validate_json(diff.model_dump_json())
        assert restored == diff
        assert restored.next_directive is not None
        assert restored.accepted_jobs[0].metadata.company == "Acme"

    def test_preferences_and_ledger_round_trip(self) -> None:
        prefs = SessionPreferences(
            target_roles=["Fractional CTO"], dealbreakers=["W2 only", "on-site"], nice_to_haves=["AWS"]
        )
        ledger = InteractionLedger(
            already_applied_ids=["abc123"], rejected_companies=["Legacy Corp"]
        )
        assert SessionPreferences.model_validate_json(prefs.model_dump_json()) == prefs
        assert InteractionLedger.model_validate_json(ledger.model_dump_json()) == ledger

    def test_all_stamped_with_contract_version(self) -> None:
        assert _job().contract_version == CONTRACT_VERSION
        assert SessionPreferences().contract_version == CONTRACT_VERSION


class TestJobIdIdempotency:
    def test_same_input_same_id(self) -> None:
        assert make_job_id("Remotive", "42") == make_job_id("remotive", "42")  # source case-insensitive

    def test_different_input_different_id(self) -> None:
        assert make_job_id("remotive", "42") != make_job_id("remotive", "43")

    def test_stable_short_hex(self) -> None:
        jid = make_job_id("greenhouse", "job-xyz")
        assert len(jid) == 16 and all(c in "0123456789abcdef" for c in jid)
