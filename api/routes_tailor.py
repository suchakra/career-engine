"""Protected tailor + résumé-export routes (Phase 10.6b).

Presentation/transport over the existing deterministic résumé assembly + renderers
(``web.resume_builder`` / ``web.resume_render``) — no domain change, no
``CONTRACT_VERSION`` bump.

- ``POST /api/tailor`` — one BYOK model call selects the JD-relevant achievements and
  writes a tailored summary + JD-aligned skills; returns the ``StructuredResume`` for
  preview. Instructions travel in the *user* prompt (injection-safe, per 9I) and are
  never persisted.
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
from typing import Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from api.deps import get_current_user_id, get_discovery_session
from api.schemas import StructuredResumeDTO, TailorRequest
from cli.app import DiscoverySession
from web.resume_builder import (
    Contact,
    RoleBlock,
    StructuredResume,
    tailor_structured_resume,
)
from web.resume_render import (
    structured_to_docx_bytes,
    structured_to_markdown,
    structured_to_pdf_bytes,
)

router = APIRouter()


def _dto_to_domain(dto: StructuredResumeDTO) -> StructuredResume:
    """Rebuild the (frozen) domain dataclass from the strict wire DTO."""
    return StructuredResume(
        contact=Contact(**dto.contact.model_dump()),
        summary=dto.summary,
        skills=list(dto.skills),
        experience=[RoleBlock(**b.model_dump()) for b in dto.experience],
        education=[RoleBlock(**b.model_dump()) for b in dto.education],
    )


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
        tailor_structured_resume,
        state,
        body.jd_text,
        contact,
        client=session.model_client,
        _instructions=body.instructions,
    )
    return StructuredResumeDTO.model_validate(asdict(resume))


_RENDER = {
    "pdf": ("application/pdf", "resume.pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "resume.docx",
    ),
    "md": ("text/markdown", "resume.md"),
}


@router.post("/api/resume/{fmt}")
async def render_resume(
    fmt: Literal["pdf", "docx", "md"],
    body: StructuredResumeDTO,
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Render a structured résumé (from the body) to the requested format's bytes.

    Requires a valid bearer token; no BYOK key needed (rendering is deterministic, no
    model call). An unknown ``fmt`` is rejected as 422 by the ``Literal`` path param.
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
