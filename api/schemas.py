"""Typed response models for the read APIs (Phase 10.2).

These are the API's PRESENTATION contract — a strict, no-extra-fields mirror of
the pure view dataclasses built in ``web/`` (``DashboardView``, ``PortfolioView``,
``JobsView`` and their cards). They live in the ``api`` package and are NOT part
of ``schema.py`` (the durable wire/state contract), so adding them triggers no
``CONTRACT_VERSION`` bump. The routes map the frozen dataclasses onto these
models explicitly so no dataclass type ever leaks onto the wire.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from web.dashboard import DashboardView
from web.jobs import JobCard, JobsView
from web.portfolio import EntryCard, PortfolioView, StoryCard


class _StrictModel(BaseModel):
    """Base for read responses: reject any field not declared here."""

    model_config = ConfigDict(extra="forbid")


class ApplicationWriteRequest(_StrictModel):
    """Request body for ``POST /api/applications`` (api-local, not ``schema.py``).

    A strict, no-extra-fields DTO the endpoint maps onto the existing
    ``web.application_store.save_tailored_application`` seam. ``applied_on`` is NOT
    part of the request: it is the injected clock computed at the endpoint boundary
    (``datetime.date.today()``), never supplied by the caller.
    """

    company: str
    job_title: str
    jd_text: str
    tailored_resume_json: str


class ExperienceWriteResponse(_StrictModel):
    """Response for ``POST /api/experience`` (api-local, not ``schema.py``).

    Confirms the persisted manual entry by echoing its ``entry_id`` and the
    ``title``/``org`` re-read from the discovery session, plus the resulting
    ``entry_count``. If the write can't be re-read, the endpoint still returns the
    echoed ``entry_id`` (with the submitted ``title``/``org``) rather than 500.
    """

    entry_id: str
    title: str
    org: str
    entry_count: int


class DashboardResponse(_StrictModel):
    """Mirror of :class:`web.dashboard.DashboardView` (display-ready)."""

    progress_meter: str
    show_nudge: bool
    nudge_message: str
    pending_actions: list[str]
    application_count: int
    can_tailor: bool
    can_start_grill: bool
    can_find_jobs: bool
    pending_actions_detail: list[dict[str, str]]

    @classmethod
    def from_view(cls, view: DashboardView) -> DashboardResponse:
        """Map a :class:`DashboardView` field-for-field onto the response."""
        return cls(
            progress_meter=view.progress_meter,
            show_nudge=view.show_nudge,
            nudge_message=view.nudge_message,
            pending_actions=list(view.pending_actions),
            application_count=view.application_count,
            can_tailor=view.can_tailor,
            can_start_grill=view.can_start_grill,
            can_find_jobs=view.can_find_jobs,
            pending_actions_detail=[dict(d) for d in view.pending_actions_detail],
        )


class StoryCardResponse(_StrictModel):
    """Mirror of :class:`web.portfolio.StoryCard`."""

    situation: str
    task: str
    action: str
    result: str
    metric_validated: bool
    story_id: str

    @classmethod
    def from_card(cls, card: StoryCard) -> StoryCardResponse:
        """Map one :class:`StoryCard` onto the response."""
        return cls(
            situation=card.situation,
            task=card.task,
            action=card.action,
            result=card.result,
            metric_validated=card.metric_validated,
            story_id=card.story_id,
        )


class EntryCardResponse(_StrictModel):
    """Mirror of :class:`web.portfolio.EntryCard`."""

    entry_id: str
    title: str
    org: str
    dates: str
    type_label: str
    status_label: str
    bullets: list[str]
    stories: list[StoryCardResponse]
    highlighted: bool
    story_count: int
    stories_target: int

    @classmethod
    def from_card(cls, card: EntryCard) -> EntryCardResponse:
        """Map one :class:`EntryCard` (and its stories) onto the response."""
        return cls(
            entry_id=card.entry_id,
            title=card.title,
            org=card.org,
            dates=card.dates,
            type_label=card.type_label,
            status_label=card.status_label,
            bullets=list(card.bullets),
            stories=[StoryCardResponse.from_card(s) for s in card.stories],
            highlighted=card.highlighted,
            story_count=card.story_count,
            stories_target=card.stories_target,
        )


class PortfolioResponse(_StrictModel):
    """Mirror of :class:`web.portfolio.PortfolioView` (``is_empty`` included)."""

    entries: list[EntryCardResponse]
    empty_text: str
    is_empty: bool

    @classmethod
    def from_view(cls, view: PortfolioView) -> PortfolioResponse:
        """Map a :class:`PortfolioView` field-for-field onto the response."""
        return cls(
            entries=[EntryCardResponse.from_card(e) for e in view.entries],
            empty_text=view.empty_text,
            is_empty=view.is_empty,
        )


class JobCardResponse(_StrictModel):
    """Mirror of :class:`web.jobs.JobCard`."""

    job_id: str
    title: str
    company: str
    location: str
    work_model: str
    employment_type: str
    url: str
    status: str
    rationale: str

    @classmethod
    def from_card(cls, card: JobCard) -> JobCardResponse:
        """Map one :class:`JobCard` onto the response."""
        return cls(
            job_id=card.job_id,
            title=card.title,
            company=card.company,
            location=card.location,
            work_model=card.work_model,
            employment_type=card.employment_type,
            url=card.url,
            status=card.status,
            rationale=card.rationale,
        )


class JobsResponse(_StrictModel):
    """Mirror of :class:`web.jobs.JobsView` (``is_empty`` included)."""

    accepted: list[JobCardResponse]
    for_review: list[JobCardResponse]
    iterations: int
    hard_rejected_count: int
    ran: bool
    empty_text: str
    is_empty: bool

    @classmethod
    def from_view(cls, view: JobsView) -> JobsResponse:
        """Map a :class:`JobsView` field-for-field onto the response."""
        return cls(
            accepted=[JobCardResponse.from_card(c) for c in view.accepted],
            for_review=[JobCardResponse.from_card(c) for c in view.for_review],
            iterations=view.iterations,
            hard_rejected_count=view.hard_rejected_count,
            ran=view.ran,
            empty_text=view.empty_text,
            is_empty=view.is_empty,
        )
