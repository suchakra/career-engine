"""Persistence for discovered jobs + the interaction ledger.

Accepted jobs are written **idempotently** keyed by :attr:`JobOpportunity.job_id`
(a content hash), so a crash/re-run never duplicates a record. The stored ids are
also what hydrates the :class:`schema.InteractionLedger` on the next run — that is
how the Primary's hard-reject gate "never re-surfaces" a job the user has already
seen (see the ledger's docstring: it gates duplicate processing).

Two implementations share one Protocol:

- :class:`InMemoryLedgerStore` — the default; no GCP needed (dev / CI / demo).
- :class:`FirestoreLedgerStore` — one subcollection per user
  (``discovered_jobs/{user_id}/jobs/{job_id}``); used with ``--firestore``.

No secrets are ever written here (only public posting facts + the AI rationale).
"""

from __future__ import annotations

from typing import Any, Protocol

from schema import InteractionLedger, JobOpportunity


class LedgerStore(Protocol):
    """Loads the interaction ledger and idempotently records accepted jobs."""

    def load_ledger(self, user_id: str) -> InteractionLedger:
        """Return the user's ledger (already-seen job_ids gate re-processing)."""
        ...

    def record_accepted(self, user_id: str, jobs: list[JobOpportunity]) -> int:
        """Persist accepted jobs idempotently; return the count of *new* writes."""
        ...

    def list_accepted(self, user_id: str) -> list[JobOpportunity]:
        """Return the user's previously accepted jobs (for display on entry)."""
        ...

    def add_rejected_company(self, user_id: str, company: str) -> None:
        """Record a company the user dismissed (future runs hard-reject it)."""
        ...


def _dedup_append(bucket: list[str], name: str) -> list[str]:
    """Append ``name`` to ``bucket`` unless a case-insensitive match already exists."""
    if name and name.lower() not in {c.lower() for c in bucket}:
        return [*bucket, name]
    return bucket


class InMemoryLedgerStore:
    """Dict-backed store for dev / CI / demo (no persistence across processes)."""

    def __init__(self) -> None:
        """Initialise empty per-user job + dismissed-company maps."""
        self._jobs: dict[str, dict[str, JobOpportunity]] = {}
        self._rejected: dict[str, list[str]] = {}

    def load_ledger(self, user_id: str) -> InteractionLedger:
        """Return the user's ledger: seen job_ids + dismissed companies."""
        return InteractionLedger(
            already_applied_ids=list(self._jobs.get(user_id, {})),
            rejected_companies=list(self._rejected.get(user_id, [])),
        )

    def record_accepted(self, user_id: str, jobs: list[JobOpportunity]) -> int:
        """Store jobs by job_id; a repeat job_id overwrites without counting as new."""
        bucket = self._jobs.setdefault(user_id, {})
        written = 0
        for job in jobs:
            if job.job_id not in bucket:
                written += 1
            bucket[job.job_id] = job
        return written

    def list_accepted(self, user_id: str) -> list[JobOpportunity]:
        """Return the user's stored jobs (insertion order)."""
        return list(self._jobs.get(user_id, {}).values())

    def add_rejected_company(self, user_id: str, company: str) -> None:
        """Record a dismissed company (case preserved; deduped case-insensitively)."""
        name = company.strip()
        if name:
            self._rejected[user_id] = _dedup_append(self._rejected.get(user_id, []), name)


class FirestoreLedgerStore:
    """Firestore-backed store: ``discovered_jobs/{user_id}/jobs/{job_id}`` (sync).

    Uses the SYNC Firestore client — the ``discover`` CLI is standalone and not
    inside the web async event loop, so the sync client is the simpler, correct
    choice here (the web/session stores use the async client for their own loop).
    """

    def __init__(self, *, collection_prefix: str = "discovered_jobs", client: Any | None = None) -> None:
        """Bind the root collection and Firestore client (defaults to the real one)."""
        if client is None:
            from config import get_firestore_client

            client = get_firestore_client()
        self._prefix = collection_prefix
        self._client: Any = client

    def _doc_ref(self, user_id: str) -> Any:
        """Parent doc ``discovered_jobs/{user_id}`` (holds dismissed companies)."""
        return self._client.collection(self._prefix).document(user_id)

    def _jobs_col(self, user_id: str) -> Any:
        return self._doc_ref(user_id).collection("jobs")

    def load_ledger(self, user_id: str) -> InteractionLedger:
        """Read stored job_ids + dismissed companies into the ledger."""
        ids = [doc.id for doc in self._jobs_col(user_id).stream()]
        snap = self._doc_ref(user_id).get()
        rejected = (snap.to_dict() or {}).get("rejected_companies", []) if snap.exists else []
        return InteractionLedger(
            already_applied_ids=ids, rejected_companies=[str(c) for c in rejected]
        )

    def record_accepted(self, user_id: str, jobs: list[JobOpportunity]) -> int:
        """Upsert each accepted job by job_id (merge); return the count of new docs."""
        col = self._jobs_col(user_id)
        written = 0
        for job in jobs:
            ref = col.document(job.job_id)
            if not ref.get().exists:
                written += 1
            ref.set(job.model_dump(mode="json"), merge=True)
        return written

    def list_accepted(self, user_id: str) -> list[JobOpportunity]:
        """Read all stored job docs back into JobOpportunity objects.

        Resilient per-record: a single malformed doc is skipped (falling back to
        the doc id as job_id when that's all that's missing) rather than blanking
        the whole list — one bad record shouldn't hide every prior match.
        """
        out: list[JobOpportunity] = []
        for doc in self._jobs_col(user_id).stream():
            data = doc.to_dict() or {}
            data.setdefault("job_id", doc.id)  # doc id IS the job_id (see record_accepted)
            try:
                out.append(JobOpportunity.model_validate(data))
            except ValueError:
                continue
        return out

    def add_rejected_company(self, user_id: str, company: str) -> None:
        """Add a dismissed company to the parent doc (read-modify-write, deduped)."""
        name = company.strip()
        if not name:
            return
        ref = self._doc_ref(user_id)
        snap = ref.get()
        existing = [str(c) for c in (snap.to_dict() or {}).get("rejected_companies", [])] if snap.exists else []
        merged = _dedup_append(existing, name)
        if merged != existing:
            ref.set({"rejected_companies": merged}, merge=True)
