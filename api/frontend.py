"""Serve the built Next.js static export (10.7 single-container topology, AD-16.10).

The frontend is an SPA (all client components → client-side auth + data), so
``next build`` emits static HTML/JS to ``frontend/out/``. FastAPI serves that at ``/``
**same-origin**, mounted AFTER the ``/api/*`` routers, so the whole product is one
Cloud Run service with no CORS. `trailingSlash` export writes each route as
``<route>/index.html``, which ``StaticFiles(html=True)`` serves directly.

The mount only happens when the export directory exists, so the API test suite and
local dev (no frontend build present) are unaffected.
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

if TYPE_CHECKING:
    from fastapi import FastAPI

_DEFAULT_DIR = "frontend/out"


class ExportStaticFiles(StaticFiles):
    """StaticFiles for a Next.js export: serve the exported 404 page on a miss."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            notfound = pathlib.Path(str(self.directory)) / "404.html"
            if notfound.is_file():
                return FileResponse(notfound, status_code=404)
        return response


def mount_frontend(app: FastAPI, directory: str = _DEFAULT_DIR) -> bool:
    """Mount the static export at '/' if the build exists. Returns True when mounted.

    Call AFTER all ``/api/*`` routers are registered — Starlette matches routes in
    order, so the API takes precedence and the static mount is the catch-all.
    """
    root = pathlib.Path(directory)
    if not root.is_dir():
        return False
    app.mount("/", ExportStaticFiles(directory=str(root), html=True), name="frontend")
    return True
