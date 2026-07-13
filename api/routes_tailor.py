"""Protected tailor + résumé-export routes (Phase 10.6b).

Presentation/transport over the existing deterministic résumé assembly + renderers
(``web.resume_builder`` / ``web.resume_render``) — no domain change, no
``CONTRACT_VERSION`` bump.

- ``POST /api/tailor`` — one BYOK model call selects the JD-relevant achievements and
  writes a tailored summary + JD-aligned skills; returns the ``StructuredResume`` for
  preview. Instructions travel in the *user* prompt (injection-safe, per 9I) and are
  never persisted.
- ``POST /api/master-resume`` — assemble the caller's MASTER résumé (every validated
  achievement, no JD tailoring). Deterministic: no model call, so *no BYOK key is
  required* — it only needs the caller's discovery state. Returns the same
  ``StructuredResume`` shape as ``/api/tailor``, so the client exports it through the
  same ``POST /api/resume/{fmt}`` renderer.
- ``POST /api/resume/{fmt}`` — render a ``StructuredResume`` (from the request body) to
  PDF / DOCX / Markdown bytes via the existing renderers. Stateless: no model call, no
  persistence. The domain renders a résumé object in one shot and only persists a
  tailored résumé when it is *saved as an application* — there is no server-side
  tailored-résumé store to ``GET``, so export is a POST-render RPC (the client passes
  back the résumé it got from ``/api/tailor`` or a master résumé) rather than a cached
  ``GET``. Adding server-side caching would be new persistence infra (deferred).

Async discipline (mirrors 10.2–10.4): the sync model call + renderers run in a
threadpool so the event loop never blocks.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

import workflows.nodes as _nodes
from api.deps import get_current_user_id, get_discovery_session, get_session_service
from api.schemas import RoleBlockDTO, StructuredResumeDTO, TailorRequest
from cli.app import DiscoverySession
from config import get_settings
from database.firestore_session import FirestoreSessionService
from schema import CareerEngineState
from web.resume_builder import (
    Contact,
    ResumeLine,
    RoleBlock,
    StructuredResume,
    master_structured_resume,
    tailor_structured_resume,
)
from web.resume_render import (
    structured_to_docx_bytes,
    structured_to_markdown,
    structured_to_pdf_bytes,
)
from web.session_loader import atry_load_latest_discovery_state

router = APIRouter()


def _block_to_domain(dto: RoleBlockDTO) -> RoleBlock:
    """Rebuild one RoleBlock, converting its lines EXPLICITLY.

    ``RoleBlock(**dto.model_dump())`` would hand the frozen dataclass a ``list[dict]`` for
    ``bullets`` — which type-checks, renders as ``{'text': …}`` in Markdown, and raises deep
    inside python-docx on export. The renderers are the last step in the product; they do not
    get to receive dicts pretending to be lines.
    """
    return RoleBlock(
        title=dto.title,
        org=dto.org,
        dates=dto.dates,
        entry_id=dto.entry_id,
        bullets=[
            ResumeLine(text=line.text, bullet_id=line.bullet_id, story_id=line.story_id)
            for line in dto.bullets
        ],
    )


def _dto_to_domain(dto: StructuredResumeDTO) -> StructuredResume:
    """Rebuild the (frozen) domain dataclass from the strict wire DTO."""
    return StructuredResume(
        contact=Contact(**dto.contact.model_dump()),
        summary=dto.summary,
        skills=list(dto.skills),
        experience=[_block_to_domain(b) for b in dto.experience],
        education=[_block_to_domain(b) for b in dto.education],
    )


def _tailor_isolated(
    state: CareerEngineState,
    jd_text: str,
    contact: Contact,
    *,
    client: object,
    instructions: str,
) -> StructuredResume:
    """Run the tailor with the module-global model-client factory saved + restored.

    ``tailor_structured_resume`` sets ``workflows.nodes._client_factory`` to this
    caller's BYOK client (a process-global). Save the previous factory and restore it
    afterwards so a BYOK client can never leak into an unrelated request. (Fully
    removing the global mutation from the domain layer is a separate follow-up; under
    concurrent requests the global is still shared — the current deploy is
    one-instance-per-user, and the isolation model is revisited in Phase 11.C.)
    """
    saved = _nodes._client_factory
    try:
        return tailor_structured_resume(
            state, jd_text, contact, client=client, _instructions=instructions  # type: ignore[arg-type]
        )
    finally:
        _nodes._client_factory = saved


@router.post("/api/tailor")
async def tailor(
    body: TailorRequest,
    session: DiscoverySession = Depends(get_discovery_session),
) -> StructuredResumeDTO:
    """Tailor the caller's portfolio to a JD and return the structured résumé.

    Requires a valid bearer token AND a BYOK key (``get_discovery_session`` → 409 if
    no key). One model call runs on the user's own quota. The tailored résumé is
    returned for preview; it is not persisted (persistence happens only when the client
    saves it as an application via ``POST /api/applications``).
    """
    state = await session.current_state()
    contact = Contact(**body.contact.model_dump()) if body.contact else Contact()
    resume = await run_in_threadpool(
        _tailor_isolated,
        state,
        body.jd_text,
        contact,
        client=session.model_client,
        instructions=body.instructions,
    )
    return StructuredResumeDTO.model_validate(asdict(resume))


@router.post("/api/master-resume")
async def master_resume(
    user_id: str = Depends(get_current_user_id),
    session_service: FirestoreSessionService = Depends(get_session_service),
) -> StructuredResumeDTO:
    """Assemble the caller's MASTER résumé — every validated achievement, no tailoring.

    Requires a valid bearer token but NOT a BYOK key: the assembly is deterministic
    (``web.resume_builder.master_structured_resume`` — no model call), so it must not be
    gated behind ``get_discovery_session``. A missing discovery session degrades to an
    empty résumé rather than an error, exactly like ``GET /api/portfolio``.

    Returned for preview/export; not persisted (the client exports it via
    ``POST /api/resume/{fmt}``).
    """
    state = await atry_load_latest_discovery_state(
        session_service,
        app_name=get_settings().app_name,
        user_id=user_id,
        reference_date=date.today().isoformat(),
    )
    resume = await run_in_threadpool(master_structured_resume, state)
    return StructuredResumeDTO.model_validate(asdict(resume))


_RENDER = {
    "pdf": ("application/pdf", "resume.pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "resume.docx",
    ),
    "md": ("text/markdown", "resume.md"),
}


@router.post(
    "/api/resume/{fmt}",
    responses={
        200: {
            "content": {
                "application/pdf": {},
                _RENDER["docx"][0]: {},
                "text/markdown": {},
            },
            "description": "The rendered résumé bytes for the requested format.",
        }
    },
)
async def render_resume(
    fmt: Literal["pdf", "docx", "md"],
    body: StructuredResumeDTO,
    _user_id: str = Depends(get_current_user_id),
) -> Response:
    """Render a structured résumé (from the body) to the requested format's bytes.

    Requires a valid bearer token (``_user_id`` is injected only to enforce auth — the
    render itself is per-request and needs no BYOK key). An unknown ``fmt`` is rejected
    as 422 by the ``Literal`` path param.
    """
    resume = _dto_to_domain(body)
    media_type, filename = _RENDER[fmt]
    disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if fmt == "md":
        return PlainTextResponse(
            structured_to_markdown(resume), media_type=media_type, headers=disposition
        )
    renderer = structured_to_pdf_bytes if fmt == "pdf" else structured_to_docx_bytes
    data = await run_in_threadpool(renderer, resume)
    return Response(content=data, media_type=media_type, headers=disposition)
