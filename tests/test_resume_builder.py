"""Tests for the structured, ATS-safe résumé builder (web/resume_builder.py)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import cast
from uuid import uuid4

import pytest

import workflows.nodes as nodes
from integration.model_client import GeminiModelClient
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType, StarStory
from tests.test_integration import ScriptedNodeClient
from web.resume_builder import (
    Contact,
    assemble_resume,
    master_structured_resume,
    tailor_structured_resume,
)


@pytest.fixture(autouse=True)
def _restore_factory() -> Iterator[None]:
    original = nodes._client_factory
    yield
    nodes._client_factory = original


def _job() -> Entry:
    return Entry(
        type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme",
        start_date="2020", end_date="2023", status=EntryStatus.GRILLED,
    )


def _edu() -> Entry:
    return Entry(
        type=ExperienceType.EDUCATION, title="BSc Computer Science", org="MIT",
        start_date="2016", end_date="2020", status=EntryStatus.SUMMARIZED,
    )


def _story(entry: Entry, result: str) -> StarStory:
    return StarStory(
        story_id=uuid4(), entry_id=str(entry.entry_id), pillar="delivery",
        result=result, metrics_validated=True,
    )


class TestMasterStructuredResume:
    def test_includes_all_validated_stories_and_profile_summary(self) -> None:
        job, edu = _job(), _edu()
        s1, s2 = _story(job, "Cut p99 latency 40%"), _story(job, "Shipped billing v2")
        state = CareerEngineState(
            work_timeline=[job, edu],
            extracted_star_stories=[s1, s2],
            professional_summary="Staff engineer.",
        )
        resume = master_structured_resume(state, contact=Contact(name="Sam"))
        assert resume.summary == "Staff engineer."
        assert resume.contact.name == "Sam"
        assert len(resume.experience) == 1
        assert len(resume.experience[0].bullets) == 2  # all validated stories, no JD selection
        assert len(resume.education) == 1
        assert resume.skills == []  # skills are JD-aligned in the tailored pass only

    def test_includes_the_users_own_bullets_from_an_ungrilled_resume(self) -> None:
        """An UPLOADED-but-ungrilled résumé must still produce a real master résumé.

        Regression: bullets were built ONLY from validated STAR stories, and a work role
        "earned a spot" only if it had them — so a freshly-parsed résumé (entries with
        bullets, no stories yet) assembled to an EMPTY document, silently discarding
        every line the user actually supplied.
        """
        job = _job()
        job = job.model_copy(update={"bullets": ["Ran the platform team", "Owned CI/CD"]})
        state = CareerEngineState(work_timeline=[job], professional_summary="Staff engineer.")

        resume = master_structured_resume(state)

        assert len(resume.experience) == 1
        assert resume.experience[0].bullets == ["Ran the platform team", "Owned CI/CD"]

    def test_story_bullets_come_first_then_the_users_own(self) -> None:
        """Quantified achievements lead; the user's remaining lines follow, deduped."""
        job = _job()
        job = job.model_copy(
            update={"bullets": ["Cut p99 latency 40%", "Mentored four engineers"]}
        )
        state = CareerEngineState(
            work_timeline=[job],
            extracted_star_stories=[_story(job, "Cut p99 latency 40%")],
        )

        bullets = master_structured_resume(state).experience[0].bullets

        # The story bullet leads. The identical entry bullet is NOT repeated, but the
        # line the story doesn't cover survives.
        assert bullets[0].startswith("Cut p99 latency 40%")
        assert "Mentored four engineers" in bullets
        assert sum(1 for b in bullets if "Cut p99 latency 40%" in b) == 1

    def test_tailored_pass_still_ignores_entry_bullets(self) -> None:
        """Only the MASTER résumé carries raw entry bullets — the JD pass selects."""
        job = _job()
        job = job.model_copy(update={"bullets": ["Ran the platform team"]})
        state = CareerEngineState(work_timeline=[job])

        resume = assemble_resume(
            state, contact=Contact(), summary="", skills=[], selected_story_ids=[]
        )

        assert resume.experience == []

    def test_empty_when_no_validated_stories(self) -> None:
        assert master_structured_resume(CareerEngineState()).is_empty

    def test_default_contact_is_blank(self) -> None:
        job = _job()
        state = CareerEngineState(
            work_timeline=[job],
            extracted_star_stories=[_story(job, "Result")],
            professional_summary="S",
        )
        assert master_structured_resume(state).contact == Contact()


class TestAssembleResume:
    def test_groups_bullets_under_role_and_separates_education(self) -> None:
        job, edu = _job(), _edu()
        s1, s2 = _story(job, "Cut p99 latency 40%"), _story(job, "Shipped billing v2")
        state = CareerEngineState(work_timeline=[job, edu], extracted_star_stories=[s1, s2])

        resume = assemble_resume(state, contact=Contact(name="Sam"), summary="S", skills=["Python"])

        assert len(resume.experience) == 1
        role = resume.experience[0]
        assert role.org == "Acme" and role.title == "Staff Engineer"
        assert role.dates == "2020 - 2023"
        assert role.bullets == ["Cut p99 latency 40%", "Shipped billing v2"]  # under the role
        assert [e.org for e in resume.education] == ["MIT"]  # education separated
        assert resume.education[0].bullets == []

    def test_only_validated_stories_and_work_roles_with_bullets(self) -> None:
        job = _job()
        empty_job = Entry(type=ExperienceType.FULL_TIME, title="Intern", org="OldCo")
        unvalidated = StarStory(entry_id=str(job.entry_id), pillar="p", result="vague", metrics_validated=False)
        valid = _story(job, "Cut cost 20%")
        state = CareerEngineState(
            work_timeline=[job, empty_job], extracted_star_stories=[unvalidated, valid]
        )
        resume = assemble_resume(state, contact=Contact(), summary="", skills=[])
        # empty_job has no validated bullets → omitted; only the validated bullet shows.
        assert [r.org for r in resume.experience] == ["Acme"]
        assert resume.experience[0].bullets == ["Cut cost 20%"]

    def test_selected_story_ids_filters_bullets(self) -> None:
        job = _job()
        s1, s2 = _story(job, "Kept"), _story(job, "Dropped")
        state = CareerEngineState(work_timeline=[job], extracted_star_stories=[s1, s2])
        resume = assemble_resume(
            state, contact=Contact(), summary="", skills=[], selected_story_ids=[str(s1.story_id)]
        )
        assert resume.experience[0].bullets == ["Kept"]

    def test_empty_when_no_stories(self) -> None:
        resume = assemble_resume(
            CareerEngineState(work_timeline=[_job()]), contact=Contact(), summary="", skills=[]
        )
        assert resume.is_empty is True

    def test_education_only_is_not_empty(self) -> None:
        """An early-career, education-only résumé must render (education counts)."""
        resume = assemble_resume(
            CareerEngineState(work_timeline=[_edu()]), contact=Contact(), summary="", skills=[]
        )
        assert resume.education and resume.is_empty is False


class TestTailorStructuredResume:
    def test_selects_and_builds_structured_resume(self) -> None:
        job = _job()
        s1 = _story(job, "Cut p99 latency 40%")
        state = CareerEngineState(work_timeline=[job, _edu()], extracted_star_stories=[s1])
        client = ScriptedNodeClient(
            responses={
                "tailoring a candidate's real": json.dumps(
                    {
                        "tailored_summary": "Systems engineer focused on latency.",
                        "skills": ["Python", "Distributed systems"],
                        "selected_achievement_ids": [str(s1.story_id)],
                    }
                )
            }
        )
        resume = tailor_structured_resume(
            state, "We need a low-latency engineer.", Contact(name="Sam"),
            client=cast(GeminiModelClient, client),
        )
        assert resume.summary.startswith("Systems engineer")
        assert resume.skills == ["Python", "Distributed systems"]
        assert resume.experience[0].bullets == ["Cut p99 latency 40%"]
        assert resume.education[0].org == "MIT"

    def test_invalid_selected_ids_fall_back_to_all_validated(self) -> None:
        """If the model returns only non-existent ids, don't drop the résumé."""
        job = _job()
        s1 = _story(job, "Cut cost 20%")
        state = CareerEngineState(work_timeline=[job], extracted_star_stories=[s1])
        client = ScriptedNodeClient(
            responses={
                "tailoring a candidate's real": json.dumps(
                    {"tailored_summary": "S", "skills": [], "selected_achievement_ids": ["bogus-id"]}
                )
            }
        )
        resume = tailor_structured_resume(
            state, "JD", Contact(), client=cast(GeminiModelClient, client)
        )
        assert resume.experience[0].bullets == ["Cut cost 20%"]  # fell back, not empty

    def test_highlighted_entry_stories_always_included(self) -> None:
        """A pinned (highlighted) experience's achievements survive even if the model
        didn't select them (4E)."""
        job_a = _job()  # Staff Engineer at Acme
        job_b = Entry(
            type=ExperienceType.FULL_TIME, title="Lead", org="BitCrafty",
            start_date="2018", end_date="2020", status=EntryStatus.GRILLED, highlighted=True,
        )
        sa, sb = _story(job_a, "Cut latency 40%"), _story(job_b, "Grew revenue 3x")
        state = CareerEngineState(work_timeline=[job_a, job_b], extracted_star_stories=[sa, sb])
        # Model selects ONLY sa; sb belongs to the pinned entry and must still appear.
        client = ScriptedNodeClient(
            responses={
                "tailoring a candidate's real": json.dumps(
                    {"tailored_summary": "S", "skills": [], "selected_achievement_ids": [str(sa.story_id)]}
                )
            }
        )
        resume = tailor_structured_resume(
            state, "JD", Contact(), client=cast(GeminiModelClient, client)
        )
        bullets = [b for role in resume.experience for b in role.bullets]
        assert "Cut latency 40%" in bullets
        assert "Grew revenue 3x" in bullets  # kept because job_b is highlighted

    def test_no_stories_returns_empty_without_calling_model(self) -> None:
        resume = tailor_structured_resume(
            CareerEngineState(work_timeline=[_job()]), "JD", Contact(),
            client=cast(GeminiModelClient, ScriptedNodeClient(responses={})),
        )
        assert resume.is_empty is True

    def test_tailor_structured_resume_appends_instructions(self) -> None:
        """_instructions text is appended to the user prompt (not system) sent to the model."""
        job = _job()
        s1 = _story(job, "Cut p99 latency 40%")
        state = CareerEngineState(work_timeline=[job], extracted_star_stories=[s1])
        client = ScriptedNodeClient(
            responses={
                "tailoring a candidate's real": json.dumps(
                    {"tailored_summary": "S", "skills": [], "selected_achievement_ids": [str(s1.story_id)]}
                )
            }
        )
        tailor_structured_resume(
            state, "JD", Contact(),
            client=cast(GeminiModelClient, client),
            _instructions="use formal tone",
        )
        assert client.calls, "model was never called"
        assert "use formal tone" in client.calls[-1]["user"]

    def test_tailor_structured_resume_empty_instructions_unchanged(self) -> None:
        """Empty _instructions leaves the system prompt exactly as STRUCTURED_TAILOR_SYSTEM_PROMPT."""
        from workflows.prompts import STRUCTURED_TAILOR_SYSTEM_PROMPT
        job = _job()
        s1 = _story(job, "Cut p99 latency 40%")
        state = CareerEngineState(work_timeline=[job], extracted_star_stories=[s1])
        client = ScriptedNodeClient(
            responses={
                "tailoring a candidate's real": json.dumps(
                    {"tailored_summary": "S", "skills": [], "selected_achievement_ids": [str(s1.story_id)]}
                )
            }
        )
        tailor_structured_resume(
            state, "JD", Contact(),
            client=cast(GeminiModelClient, client),
            _instructions="",
        )
        assert client.calls, "model was never called"
        assert client.calls[-1]["system"] == STRUCTURED_TAILOR_SYSTEM_PROMPT
        assert "Additional instructions" not in client.calls[-1]["user"]
