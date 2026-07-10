"""Tests for serving the Next.js static export (api/frontend.py — 10.7 / AD-16.10).

Network-free. A tiny fake export dir stands in for a real ``next build`` so the tests
don't depend on a Node build: the serving contract (route dir → index.html, unknown →
404 page, /api precedence, no-op when absent) is what matters.
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.frontend import mount_frontend


def _fake_export(root: pathlib.Path) -> None:
    """Write a minimal trailingSlash-style Next export tree."""
    (root / "index.html").write_text("<h1>home</h1>", encoding="utf-8")
    (root / "dashboard").mkdir()
    (root / "dashboard" / "index.html").write_text("<h1>dashboard</h1>", encoding="utf-8")
    (root / "404.html").write_text("<h1>not found</h1>", encoding="utf-8")


def test_serves_root_and_route_index(tmp_path: pathlib.Path) -> None:
    _fake_export(tmp_path)
    app = FastAPI()
    assert mount_frontend(app, directory=str(tmp_path)) is True
    client = TestClient(app)

    assert client.get("/").text == "<h1>home</h1>"
    # A route dir is served via its index.html (StaticFiles html mode).
    assert client.get("/dashboard/").text == "<h1>dashboard</h1>"


def test_unknown_path_serves_the_404_page(tmp_path: pathlib.Path) -> None:
    _fake_export(tmp_path)
    app = FastAPI()
    mount_frontend(app, directory=str(tmp_path))

    resp = TestClient(app).get("/does-not-exist/")
    assert resp.status_code == 404
    assert "not found" in resp.text


def test_api_routes_take_precedence_over_static(tmp_path: pathlib.Path) -> None:
    _fake_export(tmp_path)
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    mount_frontend(app, directory=str(tmp_path))  # mounted AFTER the API route
    assert TestClient(app).get("/api/ping").json() == {"ok": True}


def test_noop_when_export_absent(tmp_path: pathlib.Path) -> None:
    # No build present → not mounted (so it never shadows /api in tests/dev).
    assert mount_frontend(FastAPI(), directory=str(tmp_path / "missing")) is False
