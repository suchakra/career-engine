"""Tests for the open-core plugin seam (api/plugins.py — ARCHITECTURE §17 / AD-17.2).

Network-free. Verifies the core mounts an installed plugin's router, honours the
``CE_DISABLED_PLUGINS`` denylist, isolates a broken plugin, and is a no-op with none
installed — without depending on a real installed plugin package (entry points are
faked via monkeypatch).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from api import plugins


def _fake_entry(name: str, loader: Any) -> Any:
    """A stand-in for importlib.metadata.EntryPoint with ``.name`` + ``.load()``."""
    return SimpleNamespace(name=name, load=lambda: loader)


def _ping_plugin(app: FastAPI) -> None:
    """A sample plugin registration: mounts one route under /api/pro."""
    router = APIRouter()

    @router.get("/api/pro/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)


def test_registers_installed_plugin_router(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        plugins, "entry_points", lambda group: [_fake_entry("pro", _ping_plugin)]
    )
    monkeypatch.delenv("CE_DISABLED_PLUGINS", raising=False)

    app = FastAPI()
    loaded = plugins.load_plugins(app)

    assert loaded == ["pro"]
    assert TestClient(app).get("/api/pro/ping").json() == {"ok": True}


def test_no_plugins_is_a_noop(monkeypatch: Any) -> None:
    monkeypatch.setattr(plugins, "entry_points", lambda group: [])
    assert plugins.load_plugins(FastAPI()) == []


def test_disabled_plugin_is_skipped(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        plugins, "entry_points", lambda group: [_fake_entry("pro", _ping_plugin)]
    )
    monkeypatch.setenv("CE_DISABLED_PLUGINS", "pro")

    app = FastAPI()
    assert plugins.load_plugins(app) == []
    assert TestClient(app).get("/api/pro/ping").status_code == 404


def test_broken_plugin_does_not_crash_the_core(monkeypatch: Any) -> None:
    def _boom(app: FastAPI) -> None:
        raise RuntimeError("plugin blew up")

    monkeypatch.setattr(
        plugins,
        "entry_points",
        lambda group: [_fake_entry("broken", _boom), _fake_entry("pro", _ping_plugin)],
    )
    monkeypatch.delenv("CE_DISABLED_PLUGINS", raising=False)

    app = FastAPI()
    loaded = plugins.load_plugins(app)

    # The broken plugin is skipped; the healthy one still registers.
    assert loaded == ["pro"]
    assert TestClient(app).get("/api/pro/ping").json() == {"ok": True}
