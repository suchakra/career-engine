"""Jobs view-model + injectable renderer (Phase 7B).

Renders the two-agent discovery results in the web app: the Primary's ACCEPTED
(strong) and SOFT_REJECT (for-review) batches, each with the AI rationale. Same
two-layer, UI-logic-only pattern as :mod:`web.portfolio` / :mod:`web.dashboard`:

- :func:`build_jobs_view` — PURE map from a :class:`discovery.primary.DiscoveryResult`
  (a fresh run) or a list of previously-persisted jobs (on entry) → display cards.
- :func:`render_jobs` — thin map from the view-model → widgets via an injected
  ``st``-like module. The "Find jobs" trigger + preference form live in the caller
  (``streamlit_app``); this renderer only shows results (+ an optional per-job tailor
  button wired in 7C).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from discovery.primary import DiscoveryResult
from schema import JobOpportunity, MatchStatus

_EMPTY_TEXT = (
    "No matches yet. Set your preferences and hit **Find jobs** — the Scout pulls live "
    "postings and the Primary agent ranks them against your rubric."
)


@dataclass(frozen=True)
class JobCard:
    """One classified job, display-ready (no schema/agent types)."""

    job_id: str
    title: str
    company: str
    location: str
    work_model: str
    employment_type: str
    url: str
    status: str
    rationale: str


@dataclass(frozen=True)
class JobsView:
    """Display-ready discovery results (fully testable without Streamlit)."""

    accepted: list[JobCard] = field(default_factory=list)
    for_review: list[JobCard] = field(default_factory=list)
    iterations: int = 0
    hard_rejected_count: int = 0
    ran: bool = False  # True after a fresh run; False on initial (persisted) load
    empty_text: str = _EMPTY_TEXT

    @property
    def is_empty(self) -> bool:
        """True when there are no accepted or for-review cards to show."""
        return not (self.accepted or self.for_review)


def job_tailor_index(jobs: Iterable[JobOpportunity]) -> dict[str, tuple[str, str]]:
    """Map job_id → (label, JD text) for the "Tailor to this job" hand-off (7C).

    ``label`` is a human "Title — Company"; the JD text is the posting's cleaned
    ``raw_description`` that the Tailor consumes. Pure — no Streamlit.
    """
    index: dict[str, tuple[str, str]] = {}
    for job in jobs:
        label = " — ".join(p for p in (job.metadata.title, job.metadata.company) if p) or "this role"
        index[job.job_id] = (label, job.raw_description)
    return index


def _card(job: JobOpportunity) -> JobCard:
    """Map a JobOpportunity into a display-ready JobCard."""
    meta = job.metadata
    return JobCard(
        job_id=job.job_id,
        title=meta.title,
        company=meta.company,
        location=meta.location,
        work_model=meta.work_model.value,
        employment_type=meta.employment_type.value,
        url=meta.url,
        status=(job.match_status.value if job.match_status else "unknown"),
        rationale=job.ai_rationale,
    )


def build_jobs_view(
    result: DiscoveryResult | None,
    *,
    prior: list[JobOpportunity] | None = None,
    hidden_companies: set[str] | None = None,
) -> JobsView:
    """Build the Jobs view-model (pure).

    With a fresh ``result``, shows its accepted + soft-rejected batches. With no
    result (initial entry), shows previously-persisted accepted jobs (``prior``).
    ``hidden_companies`` (case-insensitive) are dropped — a "Not interested" the
    user just clicked disappears immediately (and is persisted for future runs).
    """
    hidden = {c.strip().lower() for c in (hidden_companies or set()) if c.strip()}

    def _keep(job: JobOpportunity) -> bool:
        return job.metadata.company.strip().lower() not in hidden

    if result is not None:
        return JobsView(
            accepted=[_card(j) for j in result.accepted if _keep(j)],
            for_review=[_card(j) for j in result.soft_rejected if _keep(j)],
            iterations=result.iterations,
            hard_rejected_count=result.hard_rejected_count,
            ran=True,
        )
    prior_jobs = prior or []
    # Persisted jobs were all ACCEPTED when stored; keep only ACCEPTED (positive
    # filter, so a stray HARD_REJECT/None/soft never leaks into the strong list).
    accepted = [_card(j) for j in prior_jobs if j.match_status is MatchStatus.ACCEPTED and _keep(j)]
    return JobsView(accepted=accepted, ran=False)


def _render_card(
    card: JobCard,
    *,
    st: Any,
    on_tailor: Callable[[str], None] | None,
    on_reject: Callable[[str], None] | None,
) -> None:
    """Render one job card via the injected ``st``-like module."""
    head = " — ".join(p for p in (card.title, card.company) if p) or "(untitled role)"
    st.markdown(f"**{head}**")
    meta = " · ".join(
        p for p in (card.employment_type, card.work_model, card.location) if p and p != "unknown"
    )
    if meta:
        st.caption(meta)
    if card.url:
        st.caption(card.url)
    if card.rationale:
        st.write(f"→ {card.rationale}")
    if on_tailor is not None:
        st.button(
            "Tailor résumé to this",
            key=f"tailor_job_{card.job_id}",
            on_click=lambda jid=card.job_id: on_tailor(jid),
        )
    if on_reject is not None and card.company:
        st.button(
            f"🚫 Not interested in {card.company}",
            key=f"reject_job_{card.job_id}",
            on_click=lambda co=card.company: on_reject(co),
        )


def render_jobs(
    view: JobsView,
    *,
    st: Any,
    on_tailor: Callable[[str], None] | None = None,
    on_reject: Callable[[str], None] | None = None,
) -> None:
    """Render the discovery results via an injected ``st``-like module.

    Args:
        view: The view-model from :func:`build_jobs_view`.
        st: A Streamlit-like module (real ``streamlit`` in the app; a fake in tests).
        on_tailor: Optional per-job "Tailor résumé to this" callback (7C); receives
            the ``job_id``. When ``None``, no tailor button is rendered.
        on_reject: Optional per-job "Not interested" callback (HITL); receives the
            company name (dismisses it from future runs). ``None`` → no button.
    """
    if view.ran:
        st.caption(
            f"Ran {view.iterations} iteration(s): {len(view.accepted)} strong · "
            f"{len(view.for_review)} for review · {view.hard_rejected_count} filtered out."
        )
    if view.is_empty:
        st.info(view.empty_text)
        return

    if view.accepted:
        st.subheader("✅ Strong matches")
        for card in view.accepted:
            st.divider()
            _render_card(card, st=st, on_tailor=on_tailor, on_reject=on_reject)
    if view.for_review:
        st.subheader("🟡 For review")
        for card in view.for_review:
            st.divider()
            _render_card(card, st=st, on_tailor=on_tailor, on_reject=on_reject)


__all__ = ["JobCard", "JobsView", "build_jobs_view", "job_tailor_index", "render_jobs"]
