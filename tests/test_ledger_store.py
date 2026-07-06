"""Unit tests for discovery/store.py — the InMemoryLedgerStore idempotency."""

from __future__ import annotations

from discovery.store import InMemoryLedgerStore
from schema import JobMetadata, JobOpportunity, make_job_id


def _job(ext: str) -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", ext),
        metadata=JobMetadata(title="Fractional CTO", company="Acme"),
    )


def test_record_counts_only_new_writes() -> None:
    store = InMemoryLedgerStore()
    assert store.record_accepted("u1", [_job("1"), _job("2")]) == 2
    # Re-recording the same jobs writes nothing new (idempotent by job_id).
    assert store.record_accepted("u1", [_job("1"), _job("2")]) == 0
    assert store.record_accepted("u1", [_job("2"), _job("3")]) == 1


def test_load_ledger_returns_stored_ids() -> None:
    store = InMemoryLedgerStore()
    store.record_accepted("u1", [_job("1"), _job("2")])
    ledger = store.load_ledger("u1")
    assert set(ledger.already_applied_ids) == {make_job_id("remotive", "1"), make_job_id("remotive", "2")}


def test_users_are_isolated() -> None:
    store = InMemoryLedgerStore()
    store.record_accepted("u1", [_job("1")])
    assert store.load_ledger("u2").already_applied_ids == []


def test_list_accepted_returns_stored_jobs() -> None:
    store = InMemoryLedgerStore()
    store.record_accepted("u1", [_job("1"), _job("2")])
    assert {j.job_id for j in store.list_accepted("u1")} == {
        make_job_id("remotive", "1"),
        make_job_id("remotive", "2"),
    }


def test_list_accepted_empty_for_new_user() -> None:
    assert InMemoryLedgerStore().list_accepted("nobody") == []


def test_rejected_company_persists_into_ledger() -> None:
    store = InMemoryLedgerStore()
    store.add_rejected_company("u1", "Legacy Corp")
    assert store.load_ledger("u1").rejected_companies == ["Legacy Corp"]


def test_rejected_company_deduped_case_insensitively() -> None:
    store = InMemoryLedgerStore()
    store.add_rejected_company("u1", "Acme")
    store.add_rejected_company("u1", "  acme ")  # same company, different case/space
    store.add_rejected_company("u1", "")  # blank ignored
    assert store.load_ledger("u1").rejected_companies == ["Acme"]


def test_rejected_companies_isolated_per_user() -> None:
    store = InMemoryLedgerStore()
    store.add_rejected_company("u1", "Acme")
    assert store.load_ledger("u2").rejected_companies == []
