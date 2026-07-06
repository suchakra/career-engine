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

from collections.abc import Callable
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
) -> JobsView:
    """Build the Jobs view-model (pure).

    With a fresh ``result``, shows its accepted + soft-rejected batches. With no
    result (initial entry), shows previously-persisted accepted jobs (``prior``).
    """
    if result is not None:
        return JobsView(
            accepted=[_card(j) for j in result.accepted],
            for_review=[_card(j) for j in result.soft_rejected],
            iterations=result.iterations,
            hard_rejected_count=result.hard_rejected_count,
            ran=True,
        )
    prior_jobs = prior or []
    # Persisted jobs were all ACCEPTED when stored; keep only those, defensively.
    accepted = [_card(j) for j in prior_jobs if j.match_status is not MatchStatus.SOFT_REJECT]
    return JobsView(accepted=accepted, ran=False)


def _render_card(card: JobCard, *, st: Any, on_tailor: Callable[[str], None] | None) -> None:
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


def render_jobs(
    view: JobsView,
    *,
    st: Any,
    on_tailor: Callable[[str], None] | None = None,
) -> None:
    """Render the discovery results via an injected ``st``-like module.

    Args:
        view: The view-model from :func:`build_jobs_view`.
        st: A Streamlit-like module (real ``streamlit`` in the app; a fake in tests).
        on_tailor: Optional per-job "Tailor résumé to this" callback (7C); receives
            the ``job_id``. When ``None``, no tailor button is rendered.
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
            _render_card(card, st=st, on_tailor=on_tailor)
    if view.for_review:
        st.subheader("🟡 For review")
        for card in view.for_review:
            st.divider()
            _render_card(card, st=st, on_tailor=on_tailor)


__all__ = ["JobCard", "JobsView", "build_jobs_view", "render_jobs"]
