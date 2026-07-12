"""Typed response models for the read APIs (Phase 10.2).

These are the API's PRESENTATION contract — a strict, no-extra-fields mirror of
the pure view dataclasses built in ``web/`` (``DashboardView``, ``PortfolioView``,
``JobsView`` and their cards). They live in the ``api`` package and are NOT part
of ``schema.py`` (the durable wire/state contract), so adding them triggers no
``CONTRACT_VERSION`` bump. The routes map the frozen dataclasses onto these
models explicitly so no dataclass type ever leaks onto the wire.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


class BulletCardResponse(_StrictModel):
    """Mirror of :class:`web.portfolio.BulletCard` — a bullet WITH its id (v2.9.0)."""

    bullet_id: str
    text: str


class EntryCardResponse(_StrictModel):
    """Mirror of :class:`web.portfolio.EntryCard`."""

    entry_id: str
    title: str
    org: str
    dates: str
    type_label: str
    status_label: str
    bullets: list[BulletCardResponse]
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
            bullets=[BulletCardResponse(bullet_id=b.bullet_id, text=b.text) for b in card.bullets],
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


# ── Grill transport DTOs (Phase 10.4 — SSE grill, api-local, not schema.py) ────


class GrillActionRequest(_StrictModel):
    """Request body for ``POST /api/grill`` (api-local, not ``schema.py``).

    Records the caller's input into the durable canonical session WITHOUT running
    the graph (the graph runs later on ``GET /api/grill/stream``). The user's answer
    travels in the body (never a URL query), so grill PII never lands in access logs.

    - ``start`` uses ``history`` (+ optional ``reference_date``) to create the session.
    - ``answer`` uses ``answer`` (patched as ``pending_user_answer``).
    - ``confirm`` uses neither (sets ``checkpoint_verified``).
    """

    action: Literal["start", "answer", "confirm"]
    answer: str = ""
    history: str = ""
    reference_date: str = ""


class GrillStatus(_StrictModel):
    """Response for ``GET /api/grill``: does a durable grill session already exist?

    Read-only and model-free — it reports what the session ALREADY holds
    (``current_question`` / ``checkpoint_delta_summary`` are persisted), so resuming a
    grill costs no model call and cannot re-ask a question the user already saw.

    Without this the client had no way to know a session existed: the Grill page decided
    what to render purely from in-memory state, so a fresh page load always showed the
    "upload your résumé" start card — even with a live session full of ungrilled
    entries, and even when the user had just clicked "Grill me about this".
    """

    has_session: bool
    phase: str
    frontier_label: str
    awaiting: Literal["idle", "question", "checkpoint", "complete"]
    current_question: str
    checkpoint_summary: str


class GrillSnapshot(_StrictModel):
    """Response for ``POST /api/grill``: a small post-record status snapshot.

    Computed from the durable session AFTER the record (no turn was run), so the
    client can render the "currently grilling" banner + await state before opening
    the SSE stream.
    """

    phase: str
    frontier_label: str
    awaiting: Literal["question", "checkpoint", "complete"]


class GrillTurnEvent(_StrictModel):
    """SSE payload for one completed grill turn (``event: turn`` / ``event: done``).

    Mirrors the fields of :class:`cli.app.TurnResult` plus the presentation-only
    ``phase`` (the ``PhaseStatus`` value) and ``frontier_label`` (the effective
    "currently grilling" label after the turn).
    """

    next_question: str
    checkpoint_summary: str
    is_complete: bool
    upgrade_required: bool
    upgrade_message: str
    stories_count: int
    phase: str
    frontier_label: str


class GrillErrorEvent(_StrictModel):
    """SSE payload for a mid-stream model failure (``event: error``).

    Emitted instead of letting the stream 500 when a :class:`ModelAPIError` is
    raised while running a turn, so the client can surface a friendly message and
    (when ``rate_limited``) advise trying again later.
    """

    message: str
    rate_limited: bool


# ── Tailor / résumé export (Phase 10.6b) ──────────────────────────────────────
# Strict DTOs mirroring the stdlib dataclasses in ``web.resume_builder`` (Contact,
# RoleBlock, StructuredResume). The routes convert explicitly so no dataclass ever
# lands on the wire (and FastAPI's dataclass edge cases are avoided). No CONTRACT
# bump — these are transport DTOs, not ``schema.py`` domain types.


class ContactDTO(_StrictModel):
    """Résumé header identity (mirrors ``web.resume_builder.Contact``)."""

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class RoleBlockDTO(_StrictModel):
    """One experience/education entry (mirrors ``web.resume_builder.RoleBlock``)."""

    title: str
    org: str
    dates: str
    bullets: list[str] = Field(default_factory=list)


class StructuredResumeDTO(_StrictModel):
    """A real résumé (mirrors ``web.resume_builder.StructuredResume``).

    Response of ``POST /api/tailor`` and request body of ``POST /api/resume/{fmt}``.
    """

    contact: ContactDTO
    summary: str
    skills: list[str] = Field(default_factory=list)
    experience: list[RoleBlockDTO] = Field(default_factory=list)
    education: list[RoleBlockDTO] = Field(default_factory=list)


class TailorRequest(_StrictModel):
    """Request body for ``POST /api/tailor``.

    ``jd_text`` is the already-resolved job description; ``instructions`` are placed
    in the *user* prompt (injection-safe, per 9I) and never persisted; ``contact``
    optionally overrides the résumé header (else an empty header).
    """

    jd_text: str
    instructions: str = ""
    contact: ContactDTO | None = None



# ── BYOK key management (parity P1) ───────────────────────────────────────────


class KeyWriteRequest(_StrictModel):
    """Request body for ``POST /api/key`` — the user's raw Gemini API key (BYOK).

    Never logged or echoed back; stored in Secret Manager (``ce-key-{user_id}``).
    """

    api_key: str = Field(min_length=10)


class KeyStatusResponse(_StrictModel):
    """Response for ``GET /api/key`` — whether the caller has a saved key. The raw
    key is NEVER returned."""

    has_key: bool


# ── Portfolio actions (parity P4b) ────────────────────────────────────────────


class HighlightRequest(_StrictModel):
    """Request body for ``POST /api/experience/{entry_id}/highlight``."""

    highlighted: bool


class BulletAddRequest(_StrictModel):
    """Request body for ``POST /api/experience/{entry_id}/bullet`` — append a bullet.

    ``text`` is stripped before the length check for the same reason as
    ``BulletEditRequest.new_text`` below: the store strips it too, so a blank line would
    be a silently-dropped write reported to the UI as a success.
    """

    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class BulletEditRequest(_StrictModel):
    """Request body for ``PATCH /api/experience/{entry_id}/bullet`` (parity P5).

    ``new_text`` is stripped BEFORE the length check, so a whitespace-only edit is a 422
    rather than a silent no-op: the store strips it too, and would otherwise leave the
    bullet untouched while the endpoint reported 204.

    Addressed by ``bullet_id``, not by array index (v2.9.0, AD-18.3) — an index shifts
    under any concurrent insert/delete, so a slow client could edit the wrong line.
    """

    bullet_id: str = Field(min_length=1)
    new_text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class DismissCompanyRequest(_StrictModel):
    """Request body for ``POST /api/jobs/dismiss`` (parity P5).

    Dismissal is by COMPANY, not by job: the discovery ledger hard-rejects the company
    on future runs (``discovery.store.add_rejected_company``), which is what the old
    "Not interested" affordance did.

    ``company`` is stripped before the length check (same reason as ``new_text`` above —
    the ledger strips it, so a blank name would be a silently-dropped dismissal).
    """

    company: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
