"""Tests for config.Settings environment handling."""

from __future__ import annotations

import pathlib

import pytest

from config import Settings


def test_settings_ignores_unknown_env_file_keys(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: unknown .env keys must be IGNORED, not rejected.

    The devcontainer writes git-identity vars (GIT_USER_EMAIL, GIT_COMMIT_GPGSIGN,
    …) into ``.env``. pydantic-settings reads the whole file, so without
    ``extra="ignore"`` those unknown keys raise ``extra_forbidden`` and break every
    ``get_settings()`` call (and thus the whole test suite) locally.
    """
    env = tmp_path / ".env"
    env.write_text(
        "GIT_USER_EMAIL=someone@example.com\n"
        "GIT_COMMIT_GPGSIGN=true\n"
        "SOME_UNRELATED_VAR=x\n"
        "GCP_PROJECT_ID=test-project\n"
    )
    monkeypatch.chdir(tmp_path)  # Settings reads ".env" relative to cwd

    settings = Settings()  # must NOT raise on the unrelated keys
    assert settings.gcp_project_id == "test-project"  # a real field still resolves
