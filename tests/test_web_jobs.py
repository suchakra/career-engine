"""Tests for the Jobs view-model + renderer (Phase 7B).

Two-layer UI: build_jobs_view is pure; render_jobs takes an injected fake ``st``.
No Streamlit runtime, no network.
"""

from __future__ import annotations

from typing import Any

from discovery.primary import DiscoveryResult
from schema import EmploymentType, JobMetadata, JobOpportunity, MatchStatus, WorkModel, make_job_id
from web.jobs import JobsView, build_jobs_view, job_tailor_index, render_jobs


class FakeSt:
    def __init__(self) -> None:
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.writes: list[str] = []
        self.subheaders: list[str] = []
        self.infos: list[str] = []
        self.dividers = 0
        self.buttons: list[tuple[str, dict[str, Any]]] = []

    def markdown(self, body: str) -> None:
        self.markdowns.append(body)

    def caption(self, body: str) -> None:
        self.captions.append(body)

    def write(self, body: str) -> None:
        self.writes.append(body)

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def info(self, body: str) -> None:
        self.infos.append(body)

    def divider(self) -> None:
        self.dividers += 1

    def button(self, label: str, **kwargs: Any) -> None:
        self.buttons.append((label, kwargs))


def _job(ext: str, *, title: str, company: str, status: MatchStatus, rationale: str) -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", ext),
        metadata=JobMetadata(
            title=title,
            company=company,
            work_model=WorkModel.REMOTE,
            employment_type=EmploymentType.CONTRACT,
            location="Worldwide",
            url=f"https://x/{ext}",
        ),
        raw_description="jd",
        match_status=status,
        ai_rationale=rationale,
    )


class TestBuildJobsView:
    def test_from_fresh_result(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")],
            soft_rejected=[_job("2", title="Dev", company="B", status=MatchStatus.SOFT_REJECT, rationale="maybe")],
            iterations=2,
            hard_rejected_count=3,
        )
        view = build_jobs_view(result)
        assert view.ran is True and view.iterations == 2 and view.hard_rejected_count == 3
        assert len(view.accepted) == 1 and view.accepted[0].company == "Acme"
        assert len(view.for_review) == 1 and view.for_review[0].status == "soft_reject"

    def test_from_prior_on_entry(self) -> None:
        prior = [_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")]
        view = build_jobs_view(None, prior=prior)
        assert view.ran is False
        assert len(view.accepted) == 1 and view.for_review == []

    def test_empty(self) -> None:
        view = build_jobs_view(None, prior=[])
        assert view.is_empty is True

    def test_hidden_companies_filtered(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")],
            soft_rejected=[_job("2", title="Dev", company="Globex", status=MatchStatus.SOFT_REJECT, rationale="maybe")],
        )
        view = build_jobs_view(result, hidden_companies={"acme"})  # case-insensitive
        assert [c.company for c in view.accepted] == []  # Acme hidden
        assert [c.company for c in view.for_review] == ["Globex"]

    def test_kept_soft_job_promoted_to_accepted(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")],
            soft_rejected=[_job("2", title="Dev", company="Globex", status=MatchStatus.SOFT_REJECT, rationale="maybe")],
        )
        view = build_jobs_view(result, kept_ids={make_job_id("remotive", "2")})
        assert [c.company for c in view.accepted] == ["Acme", "Globex"]  # Globex promoted
        assert view.for_review == []


class TestRenderJobs:
    def test_empty_shows_info(self) -> None:
        st = FakeSt()
        render_jobs(build_jobs_view(None, prior=[]), st=st)
        assert st.infos and not st.subheaders

    def test_renders_accepted_and_review(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="great fit")],
            soft_rejected=[_job("2", title="Dev", company="B", status=MatchStatus.SOFT_REJECT, rationale="maybe")],
            iterations=1,
        )
        st = FakeSt()
        render_jobs(build_jobs_view(result), st=st)
        assert "✅ Strong matches" in st.subheaders and "🟡 For review" in st.subheaders
        assert any("CTO — Acme" in m for m in st.markdowns)
        assert any("great fit" in w for w in st.writes)

    def test_tailor_button_calls_callback(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")]
        )
        seen: list[str] = []
        st = FakeSt()
        render_jobs(build_jobs_view(result), st=st, on_tailor=lambda jid: seen.append(jid))
        tailor = [(label, kw) for label, kw in st.buttons if label == "Tailor résumé to this"]
        assert len(tailor) == 1
        tailor[0][1]["on_click"]()
        assert seen == [make_job_id("remotive", "1")]

    def test_no_tailor_button_without_callback(self) -> None:
        result = DiscoveryResult(accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")])
        st = FakeSt()
        render_jobs(build_jobs_view(result), st=st)
        assert not any(label == "Tailor résumé to this" for label, _ in st.buttons)

    def test_reject_button_calls_callback_with_company(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")]
        )
        seen: list[str] = []
        st = FakeSt()
        render_jobs(build_jobs_view(result), st=st, on_reject=lambda co: seen.append(co))
        reject = [(label, kw) for label, kw in st.buttons if "Not interested" in label]
        assert len(reject) == 1
        reject[0][1]["on_click"]()
        assert seen == ["Acme"]

    def test_keep_button_on_for_review_only_and_calls_back(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")],
            soft_rejected=[_job("2", title="Dev", company="Globex", status=MatchStatus.SOFT_REJECT, rationale="maybe")],
        )
        seen: list[str] = []
        st = FakeSt()
        render_jobs(build_jobs_view(result), st=st, on_keep=lambda jid: seen.append(jid))
        keep = [(label, kw) for label, kw in st.buttons if label == "👍 Keep this"]
        assert len(keep) == 1  # only the for-review card, not the strong match
        keep[0][1]["on_click"]()
        assert seen == [make_job_id("remotive", "2")]

    def test_no_reject_button_without_callback(self) -> None:
        result = DiscoveryResult(
            accepted=[_job("1", title="CTO", company="Acme", status=MatchStatus.ACCEPTED, rationale="fit")]
        )
        st = FakeSt()
        render_jobs(build_jobs_view(result), st=st)
        assert not any("Not interested" in label for label, _ in st.buttons)


def test_jobs_view_default_is_empty() -> None:
    assert JobsView().is_empty is True


class TestJobTailorIndex:
    def test_maps_job_id_to_label_and_jd(self) -> None:
        job = JobOpportunity(
            job_id=make_job_id("remotive", "1"),
            metadata=JobMetadata(title="Fractional CTO", company="Acme"),
            raw_description="Lead cloud + AI.",
        )
        index = job_tailor_index([job])
        label, jd = index[make_job_id("remotive", "1")]
        assert label == "Fractional CTO — Acme"
        assert jd == "Lead cloud + AI."

    def test_empty_input(self) -> None:
        assert job_tailor_index([]) == {}
