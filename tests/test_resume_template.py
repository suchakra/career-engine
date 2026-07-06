"""Tests for the classic_resume.html Jinja2 template (WS 9D).

These tests render the template directly via Jinja2 to check structural
requirements (Experience, Skills, Education sections) and also verify that the
PDF render pipeline works end-to-end with a StructuredResume fixture.
"""

from __future__ import annotations

import pathlib

from jinja2 import Environment, FileSystemLoader, select_autoescape

from web.resume_builder import Contact, RoleBlock, StructuredResume

_TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "templates"


def _render_template(resume: StructuredResume) -> str:
    """Render classic_resume.html with StructuredResume data via Jinja2."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "htm"]),
        keep_trailing_newline=True,
    )
    template = env.get_template("classic_resume.html")
    return template.render(
        candidate_name=resume.contact.name,
        candidate_email=resume.contact.email,
        candidate_phone=resume.contact.phone,
        candidate_location=resume.contact.location,
        candidate_linkedin=resume.contact.links[0] if resume.contact.links else "",
        summary=resume.summary,
        target_competencies=[],
        stories_by_pillar={},
        experience=resume.experience,
        skills=resume.skills,
        education=resume.education,
    )


_FIXTURE_RESUME = StructuredResume(
    contact=Contact(
        name="Alex Chen",
        email="alex@example.com",
        phone="555-0200",
        location="San Francisco, CA",
        links=["linkedin.com/in/alexchen"],
    ),
    summary="Full-stack engineer with 8 years building distributed systems.",
    skills=["Python", "Kubernetes", "PostgreSQL"],
    experience=[
        RoleBlock(
            title="Senior Engineer",
            org="TechCorp",
            dates="2021 - present",
            bullets=["Reduced deploy time by 60% via CI/CD overhaul."],
        )
    ],
    education=[
        RoleBlock(
            title="BSc Computer Science",
            org="Stanford University",
            dates="2012 - 2016",
        )
    ],
)


def test_resume_template_has_experience_section() -> None:
    """Rendered HTML contains the employer name and bullet text inside a <li>."""
    html = _render_template(_FIXTURE_RESUME)
    assert "TechCorp" in html
    assert "<li>" in html
    assert "Reduced deploy time by 60% via CI/CD overhaul." in html


def test_resume_template_has_skills_section() -> None:
    """Rendered HTML contains at least one skill keyword."""
    html = _render_template(_FIXTURE_RESUME)
    assert "Python" in html


def test_resume_template_has_education_section() -> None:
    """Rendered HTML contains the degree field value."""
    html = _render_template(_FIXTURE_RESUME)
    assert "BSc Computer Science" in html


def test_resume_renders_to_pdf_without_error() -> None:
    """PDF render function returns non-empty bytes for a StructuredResume fixture."""
    from web.resume_render import structured_to_pdf_bytes

    pdf_bytes = structured_to_pdf_bytes(_FIXTURE_RESUME)
    assert len(pdf_bytes) > 0
