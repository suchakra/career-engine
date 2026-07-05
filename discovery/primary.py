"""Primary agent — the stateful Evaluator/Orchestrator of the A2A loop.

The Primary holds the session's :class:`schema.SessionPreferences` and
:class:`schema.InteractionLedger` and drives a **bounded adversarial loop** with
the stateless :class:`discovery.scout.Scout`:

    directive → Scout.fetch → evaluate → EvaluationDiff(next_directive) → …

Each iteration classifies the fetched batch:

1. **Deterministic HARD_REJECT gate** (no model, idempotent, cheap): drop jobs the
   ledger says are already-applied or from a rejected company, plus any absolute
   dealbreaker keyword hit. This is the safety rail that never re-surfaces noise.
2. **Agentic evaluation** of the survivors → ACCEPTED / SOFT_REJECT + a one-line
   ``ai_rationale``. This is the expensive reasoning step, routed to the
   REASONING_HIGH capability (Pro on BYOK). It is **injectable** via
   :class:`BatchEvaluator`; the default :class:`HeuristicEvaluator` is deterministic
   and key-free so the whole pipeline is demoable and testable without a key, while
   :class:`ModelEvaluator` plugs in real Gemini reasoning when a key is present.

The loop terminates when enough ACCEPTED jobs are collected or after
``max_iterations`` (default 3) — bounding cost and guaranteeing progress.

``evaluate_batch`` is a pure function (easy to unit-test); ``PrimaryAgent.discover``
is the async orchestrator that accumulates results and refines the directive.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from config import AccessMode
from discovery.scout import Scout
from integration.model_client import GeminiModelClient, ModelAPIError
from models.registry import get_registry
from schema import (
    Capability,
    EvaluationDiff,
    InteractionLedger,
    JobOpportunity,
    MatchStatus,
    ScoutBatchStatus,
    ScoutDirective,
    SessionPreferences,
)

_DEFAULT_MAX_ITERATIONS = 3
_DEFAULT_DESIRED_TOTAL = 5

Classification = dict[str, tuple[MatchStatus, str]]
"""Map of job_id → (ACCEPTED|SOFT_REJECT, one-line rationale)."""


@runtime_checkable
class BatchEvaluator(Protocol):
    """Anything that classifies a batch of survivors into ACCEPTED / SOFT_REJECT.

    Implemented by the deterministic :class:`HeuristicEvaluator` and the agentic
    :class:`ModelEvaluator`; test doubles satisfy it structurally.
    """

    def classify(self, jobs: list[JobOpportunity], prefs: SessionPreferences) -> Classification:
        """Return job_id → (status, rationale) for every input job."""
        ...


# ── Deterministic ledger / dealbreaker gate ───────────────────────────────────


def hard_reject_reason(
    job: JobOpportunity,
    prefs: SessionPreferences,
    ledger: InteractionLedger,
) -> str | None:
    """Return a HARD_REJECT rationale if the job violates the ledger/dealbreakers, else None.

    Deterministic and side-effect-free — the cheap safety rail that runs before any
    model call so already-applied / dismissed / absolutely-excluded jobs are dropped
    without spending inference.
    """
    if job.job_id in ledger.already_applied_ids:
        return "Already applied (ledger)."
    company = job.metadata.company.strip().lower()
    if company and any(company == c.strip().lower() for c in ledger.rejected_companies):
        return f"Company previously dismissed: {job.metadata.company}."
    haystack = f"{job.metadata.title}\n{job.raw_description}".lower()
    for term in _dealbreaker_terms(prefs):
        if term and term in haystack:
            return f"Dealbreaker matched: {term!r}."
    return None


def _dealbreaker_terms(prefs: SessionPreferences) -> list[str]:
    """Extract short, matchable keyword tokens from free-text dealbreakers.

    Dealbreakers are phrases ("rigid 100% on-site"); we match on a few salient
    lowercased tokens so an obvious on-site/maintenance posting is dropped
    deterministically. Nuanced judgement is left to the agentic evaluator.
    """
    tokens: list[str] = []
    for db in prefs.dealbreakers:
        low = db.strip().lower()
        if not low:
            continue
        # Keep the whole phrase only if it's short; otherwise it rarely matches
        # verbatim, so we also add a couple of salient single words.
        if len(low.split()) <= 3:
            tokens.append(low)
        for word in ("on-site", "onsite", "maintenance", "middle-management", "bureaucratic"):
            if word in low:
                tokens.append(word)
    return tokens


# ── Injectable batch evaluators (agentic vs deterministic) ─────────────────────


class HeuristicEvaluator:
    """Deterministic, key-free evaluator (default; keeps the pipeline demoable).

    ACCEPTED when a posting mentions any target-role / nice-to-have term, else
    SOFT_REJECT. Weak by design — a real key swaps in :class:`ModelEvaluator`.
    """

    def classify(self, jobs: list[JobOpportunity], prefs: SessionPreferences) -> Classification:
        """Classify survivors into ACCEPTED / SOFT_REJECT with a short rationale."""
        wanted = [t.strip().lower() for t in [*prefs.target_roles, *prefs.nice_to_haves] if t.strip()]
        out: Classification = {}
        for job in jobs:
            hay = f"{job.metadata.title}\n{job.raw_description}".lower()
            hits = sorted({t for t in wanted if t in hay})
            if hits:
                shown = ", ".join(hits[:3])
                out[job.job_id] = (MatchStatus.ACCEPTED, f"Matches your priorities: {shown}.")
            else:
                out[job.job_id] = (
                    MatchStatus.SOFT_REJECT,
                    "No explicit match to your target roles / nice-to-haves; kept for review.",
                )
        return out


_EVAL_SYSTEM_PROMPT = """\
You are a career-fit evaluator for a single candidate. You are given the
candidate's preferences and a batch of job postings. For EACH posting, decide:

- "accepted": clearly fits the candidate's target roles and most priorities.
- "soft_reject": plausible but misses a soft preference (kept for the user to review).

Do NOT output "hard_reject" — absolute dealbreakers were already filtered out.

Output rules (mandatory):
- Output ONLY a single-line JSON array, no prose, no code fences.
- Each element: {"job_id": "<id>", "status": "accepted"|"soft_reject", "rationale": "<one short sentence>"}.
- Include every job_id from the input exactly once.
- Rationale must be one plain sentence explaining the decision against the preferences.
"""


class ModelEvaluator:
    """Agentic evaluator using the REASONING_HIGH capability (Pro on BYOK).

    One model call classifies the whole batch (cost-bounded). Any parse/API failure
    falls back to the deterministic :class:`HeuristicEvaluator`, so a flaky model
    never crashes discovery.
    """

    def __init__(self, client: GeminiModelClient, *, access_mode: AccessMode = AccessMode.BYOK) -> None:
        """Bind the Gemini client and the access mode that routes the model id."""
        self._client = client
        self._access_mode = access_mode
        self._fallback = HeuristicEvaluator()

    def _model_id(self) -> str:
        resolved = get_registry().get_model_id(
            Capability.REASONING_HIGH, access_mode=self._access_mode
        )
        if not isinstance(resolved, str):
            # REASONING_HIGH is always mapped, so this is unreachable in practice;
            # treat any non-str as a config error → heuristic fallback in classify.
            raise ValueError(f"No model mapped for REASONING_HIGH: {resolved}")
        return resolved

    def classify(self, jobs: list[JobOpportunity], prefs: SessionPreferences) -> Classification:
        """Classify the batch via one model call; fall back to heuristic on failure."""
        if not jobs:
            return {}
        user = json.dumps(
            {
                "preferences": {
                    "target_roles": prefs.target_roles,
                    "nice_to_haves": prefs.nice_to_haves,
                    "dealbreakers": prefs.dealbreakers,
                },
                "postings": [
                    {
                        "job_id": j.job_id,
                        "title": j.metadata.title,
                        "company": j.metadata.company,
                        "employment_type": j.metadata.employment_type.value,
                        "work_model": j.metadata.work_model.value,
                        "location": j.metadata.location,
                        "description": j.raw_description[:1500],
                    }
                    for j in jobs
                ],
            }
        )
        try:
            raw = self._client.generate(self._model_id(), _EVAL_SYSTEM_PROMPT, user)
            parsed = _parse_classification(raw, {j.job_id for j in jobs})
        except (ModelAPIError, ValueError):
            return self._fallback.classify(jobs, prefs)
        # Any job the model omitted defaults to a safe SOFT_REJECT.
        for job in jobs:
            parsed.setdefault(
                job.job_id,
                (MatchStatus.SOFT_REJECT, "Not classified by the model; kept for review."),
            )
        return parsed


def _parse_classification(raw: str, valid_ids: set[str]) -> Classification:
    """Parse the model's JSON array into a Classification, ignoring unknown ids.

    Raises ValueError if the payload is not a JSON array (the caller then falls
    back to the heuristic evaluator).
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("[") : text.rfind("]") + 1]
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("classification payload is not a JSON array")
    out: Classification = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        jid = str(item.get("job_id", ""))
        if jid not in valid_ids:
            continue
        status = MatchStatus.ACCEPTED if str(item.get("status")) == "accepted" else MatchStatus.SOFT_REJECT
        rationale = str(item.get("rationale", "")).strip() or "No rationale provided."
        out[jid] = (status, rationale)
    return out


# ── Pure batch evaluation → EvaluationDiff ─────────────────────────────────────


def evaluate_batch(
    jobs: list[JobOpportunity],
    *,
    prefs: SessionPreferences,
    ledger: InteractionLedger,
    evaluator: BatchEvaluator,
    remaining: int,
    prev_directive: ScoutDirective,
) -> EvaluationDiff:
    """Classify one Scout batch and produce the A2A :class:`EvaluationDiff`.

    Pure and deterministic given a deterministic ``evaluator``. Applies the
    hard-reject gate first, classifies survivors, stamps ``match_status`` +
    ``ai_rationale`` on each returned job, and computes the refined
    ``next_directive`` (``None`` when this batch already met ``remaining``).
    """
    survivors: list[JobOpportunity] = []
    hard_reject_companies: set[str] = set()
    hard_rejected = 0
    for job in jobs:
        reason = hard_reject_reason(job, prefs, ledger)
        if reason is None:
            survivors.append(job)
            continue
        hard_rejected += 1
        if job.metadata.company.strip():
            hard_reject_companies.add(job.metadata.company.strip())

    classification = evaluator.classify(survivors, prefs)

    accepted: list[JobOpportunity] = []
    soft: list[JobOpportunity] = []
    reject_companies: set[str] = set(hard_reject_companies)
    for job in survivors:
        status, rationale = classification.get(
            job.job_id, (MatchStatus.SOFT_REJECT, "Unclassified; kept for review.")
        )
        stamped = job.model_copy(update={"match_status": status, "ai_rationale": rationale})
        if status is MatchStatus.ACCEPTED:
            accepted.append(stamped)
        else:
            soft.append(stamped)
            # Steer the next iteration away from companies that missed this round
            # (exact-dup postings are already deduped by job_id in the loop).
            if job.metadata.company.strip():
                reject_companies.add(job.metadata.company.strip())

    if accepted and not soft and hard_rejected == 0:
        batch_status = ScoutBatchStatus.APPROVE_BATCH
    elif accepted:
        batch_status = ScoutBatchStatus.PARTIAL_ACCEPT
    else:
        batch_status = ScoutBatchStatus.REJECT_BATCH

    still_needed = remaining - len(accepted)
    next_directive: ScoutDirective | None = None
    if still_needed > 0:
        next_directive = _refine_directive(prev_directive, reject_companies, still_needed)

    return EvaluationDiff(
        status=batch_status,
        accepted_jobs=accepted,
        soft_rejected_jobs=soft,
        next_directive=next_directive,
    )


def _refine_directive(
    prev: ScoutDirective, exclude_companies: Iterable[str], still_needed: int
) -> ScoutDirective:
    """Refine the directive for the next iteration (adversarial narrowing).

    Folds hard-rejected companies into the exclusion set and resets the quota to
    what's still missing, so each loop iteration explores away from known misses.
    """
    merged = sorted({*prev.exclude_companies, *(c.strip() for c in exclude_companies if c.strip())})
    note = (
        f"Refined: excluding {len(merged)} dismissed compan{'y' if len(merged) == 1 else 'ies'}; "
        f"seeking {still_needed} more match(es)."
    )
    return prev.model_copy(
        update={
            "exclude_companies": merged,
            "desired_count": max(1, still_needed),
            "adjustment_note": note,
        }
    )


# ── Orchestrating agent (stateful) ────────────────────────────────────────────


@dataclass
class DiscoveryResult:
    """The accumulated outcome of a bounded discovery run."""

    accepted: list[JobOpportunity] = field(default_factory=list)
    soft_rejected: list[JobOpportunity] = field(default_factory=list)
    iterations: int = 0
    hard_rejected_count: int = 0


class PrimaryAgent:
    """Stateful orchestrator: runs the bounded A2A loop with the Scout.

    Args:
        prefs: The session evaluation rubric.
        ledger: Historical state gating duplicate processing.
        scout: The stateless Fetcher.
        evaluator: Batch classifier (defaults to the key-free heuristic).
        max_iterations: Hard cap on Scout round-trips (default 3).
        desired_total: Target number of ACCEPTED jobs to stop early at.
    """

    def __init__(
        self,
        *,
        prefs: SessionPreferences,
        ledger: InteractionLedger,
        scout: Scout,
        evaluator: BatchEvaluator | None = None,
        max_iterations: int = _DEFAULT_MAX_ITERATIONS,
        desired_total: int = _DEFAULT_DESIRED_TOTAL,
    ) -> None:
        """Initialise the Primary with its preferences, ledger, and Scout."""
        self._prefs = prefs
        self._ledger = ledger
        self._scout = scout
        self._evaluator: BatchEvaluator = evaluator or HeuristicEvaluator()
        self._max_iterations = max(1, max_iterations)
        self._desired_total = max(1, desired_total)

    def initial_directive(self) -> ScoutDirective:
        """Build the first ScoutDirective from the session preferences."""
        query = " ".join(self._prefs.target_roles).strip() or "engineer"
        return ScoutDirective(query=query, desired_count=self._desired_total)

    async def discover(self) -> DiscoveryResult:
        """Run the bounded adversarial loop and return the accumulated result.

        Dedupes postings across iterations by ``job_id`` (the source may overlap),
        accumulates ACCEPTED / SOFT_REJECT jobs, and stops at ``desired_total`` or
        after ``max_iterations`` — whichever comes first.
        """
        result = DiscoveryResult()
        seen: set[str] = set()
        directive = self.initial_directive()

        for _ in range(self._max_iterations):
            result.iterations += 1
            batch = await self._scout.fetch(directive)
            fresh = [j for j in batch if j.job_id not in seen]
            seen.update(j.job_id for j in fresh)

            remaining = self._desired_total - len(result.accepted)
            diff = evaluate_batch(
                fresh,
                prefs=self._prefs,
                ledger=self._ledger,
                evaluator=self._evaluator,
                remaining=remaining,
                prev_directive=directive,
            )
            result.accepted.extend(diff.accepted_jobs)
            result.soft_rejected.extend(diff.soft_rejected_jobs)
            result.hard_rejected_count += (
                len(fresh) - len(diff.accepted_jobs) - len(diff.soft_rejected_jobs)
            )

            if len(result.accepted) >= self._desired_total or diff.next_directive is None:
                break
            directive = diff.next_directive

        return result
