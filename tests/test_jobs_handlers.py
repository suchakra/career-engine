"""Tests for the Jobs-view Streamlit handlers in web/streamlit_app.

The module is import-safe (``main()`` runs only under a real Streamlit runtime), so
the handlers can be exercised with a fake ``st`` (a plain dict for ``session_state``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import web.streamlit_app as app
from discovery.store import InMemoryLedgerStore
from schema import JobMetadata, JobOpportunity, MatchStatus, make_job_id


def _soft_job() -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", "1"),
        metadata=JobMetadata(title="Dev", company="Globex"),
        raw_description="jd",
        match_status=MatchStatus.SOFT_REJECT,
    )


def _fake_st(session_state: dict[str, Any]) -> Any:
    warnings: list[str] = []
    return SimpleNamespace(session_state=session_state, warning=warnings.append, warnings=warnings)


def test_keep_job_records_accepted_and_promotes(monkeypatch: Any) -> None:
    job = _soft_job()
    store = InMemoryLedgerStore()
    ss: dict[str, Any] = {"_jobs_by_id": {job.job_id: job}, "_jobs_reject_store": store}
    monkeypatch.setattr(app, "st", _fake_st(ss))

    app._keep_job(user_id="u1", job_id=job.job_id)

    assert job.job_id in ss["_jobs_kept"]  # promoted in-session (moves to Strong matches)
    saved = store.list_accepted("u1")
    assert len(saved) == 1
    assert saved[0].match_status is MatchStatus.ACCEPTED  # persisted AS ACCEPTED, not soft


def test_keep_job_stays_kept_even_if_persist_fails(monkeypatch: Any) -> None:
    class _FailingStore(InMemoryLedgerStore):
        def record_accepted(self, user_id: str, jobs: list[JobOpportunity]) -> int:
            raise RuntimeError("backend down")

    job = _soft_job()
    ss: dict[str, Any] = {"_jobs_by_id": {job.job_id: job}, "_jobs_reject_store": _FailingStore()}
    st = _fake_st(ss)
    monkeypatch.setattr(app, "st", st)

    app._keep_job(user_id="u1", job_id=job.job_id)

    assert job.job_id in ss["_jobs_kept"]  # kept in session regardless
    assert st.warnings  # user is warned that saving failed


def test_keep_job_missing_job_is_noop(monkeypatch: Any) -> None:
    ss: dict[str, Any] = {"_jobs_by_id": {}, "_jobs_reject_store": InMemoryLedgerStore()}
    monkeypatch.setattr(app, "st", _fake_st(ss))
    app._keep_job(user_id="u1", job_id="unknown")  # must not raise
    assert "unknown" in ss["_jobs_kept"]  # still recorded in the session kept-set
