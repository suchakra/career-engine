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


class InMemoryLedgerStore:
    """Dict-backed store for dev / CI / demo (no persistence across processes)."""

    def __init__(self) -> None:
        """Initialise an empty per-user job map."""
        self._jobs: dict[str, dict[str, JobOpportunity]] = {}

    def load_ledger(self, user_id: str) -> InteractionLedger:
        """Return a ledger whose already_applied_ids are this user's stored jobs."""
        return InteractionLedger(already_applied_ids=list(self._jobs.get(user_id, {})))

    def record_accepted(self, user_id: str, jobs: list[JobOpportunity]) -> int:
        """Store jobs by job_id; a repeat job_id overwrites without counting as new."""
        bucket = self._jobs.setdefault(user_id, {})
        written = 0
        for job in jobs:
            if job.job_id not in bucket:
                written += 1
            bucket[job.job_id] = job
        return written


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

    def _jobs_col(self, user_id: str) -> Any:
        return self._client.collection(self._prefix).document(user_id).collection("jobs")

    def load_ledger(self, user_id: str) -> InteractionLedger:
        """Read the stored job_ids into the ledger's already_applied_ids."""
        ids = [doc.id for doc in self._jobs_col(user_id).stream()]
        return InteractionLedger(already_applied_ids=ids)

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
