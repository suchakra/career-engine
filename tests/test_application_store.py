"""Unit tests for web/application_store.py — save-as-tracked-application (5B).

Uses an in-memory fake WorkspaceStore, so the read-modify-write path is exercised
with no GCP.
"""

from __future__ import annotations

import json

from schema import Application, ApplicationStatus, PendingAction, UserWorkspace
from web.application_store import build_application, save_tailored_application
from web.resume_builder import Contact, ResumeLine, RoleBlock, StructuredResume


class _FakeStore:
    """In-memory WorkspaceStore double keyed by user_id."""

    def __init__(self) -> None:
        self._by_user: dict[str, UserWorkspace] = {}

    def load(self, user_id: str) -> UserWorkspace:
        # Return the stored workspace or a fresh empty one (mirrors Firestore store).
        return self._by_user.get(user_id, UserWorkspace())

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        self._by_user[user_id] = workspace


def test_build_application_maps_fields_and_trims() -> None:
    app = build_application(
        company="  Acme AI ",
        job_title="  Fractional CTO ",
        jd_text="Lead cloud + AI.",
        tailored_resume_json='{"summary": "x"}',
        applied_on="2026-07-05",
    )
    assert app.company == "Acme AI" and app.job_title == "Fractional CTO"
    assert app.status is ApplicationStatus.APPLIED
    assert app.applied_on == "2026-07-05"
    assert app.jd_text == "Lead cloud + AI." and app.tailored_resume_json == '{"summary": "x"}'


def test_save_appends_and_persists() -> None:
    store = _FakeStore()
    app = save_tailored_application(
        store,
        user_id="u1",
        company="Acme",
        job_title="CTO",
        jd_text="JD",
        tailored_resume_json="{}",
        applied_on="2026-07-05",
    )
    ws = store.load("u1")
    assert len(ws.applications) == 1
    assert ws.applications[0].application_id == app.application_id
    assert ws.applications[0].company == "Acme"


def test_save_coexists_with_existing_applications_and_pending_actions() -> None:
    store = _FakeStore()
    existing = Application(company="Old Co", job_title="Eng", applied_on="2026-06-01")
    # A pending action from the async sweep must survive the read-modify-write.
    store.save(
        "u1",
        UserWorkspace(applications=[existing], pending_actions=[PendingAction(reason="follow up")]),
    )

    save_tailored_application(
        store,
        user_id="u1",
        company="New Co",
        job_title="Principal",
        jd_text="JD",
        tailored_resume_json="{}",
        applied_on="2026-07-05",
    )
    ws = store.load("u1")
    assert [a.company for a in ws.applications] == ["Old Co", "New Co"]
    assert len(ws.pending_actions) == 1 and ws.pending_actions[0].reason == "follow up"


def test_saves_real_structured_resume_json() -> None:
    # Exercise the ACTUAL serialization path the UI uses (StructuredResume.to_json),
    # not a string literal — this is what caught the model_dump_json() bug.
    resume = StructuredResume(
        contact=Contact(name="Ada", email="ada@example.com", links=["https://x/ada"]),
        summary="Fractional CTO.",
        skills=["AWS", "MCP"],
        experience=[RoleBlock(title="CTO", org="Acme", dates="2020 - present", bullets=[ResumeLine(text="Led X.")])],
        education=[],
    )
    store = _FakeStore()
    app = save_tailored_application(
        store,
        user_id="u1",
        company="Acme",
        job_title="CTO",
        jd_text="JD",
        tailored_resume_json=resume.to_json(),
        applied_on="2026-07-05",
    )
    # The persisted JSON is valid and round-trips the résumé content.
    parsed = json.loads(app.tailored_resume_json)
    assert parsed["contact"]["name"] == "Ada"
    assert parsed["skills"] == ["AWS", "MCP"]
    assert parsed["experience"][0]["org"] == "Acme"


def test_save_does_not_mutate_the_loaded_workspace_in_place() -> None:
    # A store may return a cached/shared instance; the save must copy-on-write so a
    # failed save can't leak the new application into the caller's held reference.
    store = _FakeStore()
    original = UserWorkspace()
    store.save("u1", original)  # _FakeStore returns this exact instance from load()
    save_tailored_application(
        store, user_id="u1", company="A", job_title="X",
        jd_text="", tailored_resume_json="{}", applied_on="2026-07-05",
    )
    assert original.applications == []          # untouched
    assert len(store.load("u1").applications) == 1  # persisted copy has it


def test_each_save_is_a_distinct_application() -> None:
    store = _FakeStore()
    a = save_tailored_application(
        store, user_id="u1", company="A", job_title="X",
        jd_text="", tailored_resume_json="{}", applied_on="2026-07-05",
    )
    b = save_tailored_application(
        store, user_id="u1", company="A", job_title="X",
        jd_text="", tailored_resume_json="{}", applied_on="2026-07-05",
    )
    ws = store.load("u1")
    assert len(ws.applications) == 2 and a.application_id != b.application_id
