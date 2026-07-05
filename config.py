"""CareerEngine configuration: settings, CONTRACT_VERSION, and client factories.

Phase 0 — Contract Freeze.  No real model calls; no live cloud I/O in this module.
The factories return typed client objects so downstream code can be type-checked;
they raise if the required env-var / credential is absent.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

# ── Contract version ──────────────────────────────────────────────────────────
CONTRACT_VERSION: str = "2.6.0"
"""Semver version of the shared schema contract.

Every persisted document and every inter-agent message envelope is stamped
with this string.  A consumer that sees a different major version MUST refuse
rather than mis-parse.  Bump MINOR for backward-compatible additions; bump
MAJOR for breaking changes (rare; requires coordinated migration).
"""


# ── Access mode ───────────────────────────────────────────────────────────────
class AccessMode(StrEnum):
    """Controls which Gemini key is used for inference."""

    FREE = "FREE"
    """Platform-managed key; restricted to Flash / Flash-Lite free tier."""

    BYOK = "BYOK"
    """User's own Gemini key fetched from Secret Manager at runtime."""


# ── Settings ──────────────────────────────────────────────────────────────────
class Settings(BaseSettings):
    """Central configuration loaded from environment variables / .env."""

    # Google Cloud
    gcp_project_id: str = Field(default="", description="GCP project ID")
    gcp_region: str = Field(default="us-central1", description="GCP region")
    firebase_project_id: str = Field(default="", description="Firebase project ID")

    # Gemini (platform-managed key for Free Mode)
    gemini_api_key: str = Field(default="", description="Platform Gemini API key (Free Mode)")

    # Access mode
    access_mode: AccessMode = Field(
        default=AccessMode.FREE,
        description="FREE=managed key, BYOK=user key from Secret Manager",
    )

    # Application
    app_name: str = Field(default="career-engine", description="ADK app name / Firestore namespace")

    # Observability — a per-request model timeout so a network stall surfaces as a
    # loud error instead of hanging the discovery graph indefinitely.
    model_timeout_seconds: float = Field(
        default=60.0, description="Per-request timeout for real model calls (seconds)."
    )

    # Developer escape hatch — local dev only; never used in production
    dev_user_id: str = Field(
        default="",
        description="Local dev escape hatch: bypass Identity Platform (dev only)",
    )
    dev_gemini_key: str = Field(
        default="",
        description="Local dev escape hatch: bypass Secret Manager (dev only)",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


# ── Client factories ──────────────────────────────────────────────────────────
# google-cloud-firestore and google-cloud-secret-manager are in pyproject.toml
# but may not be installed in the Phase-0 dev environment.  Return type is Any
# so the module type-checks without the cloud packages installed; Phase 1 installs
# them and can narrow the types in the concrete implementations.


def get_firestore_client() -> Any:
    """Return an authenticated Firestore client (google.cloud.firestore.Client).

    Raises ImportError if google-cloud-firestore is not installed.
    Raises OSError if no GCP credentials can be resolved.
    """
    try:
        import google.cloud.firestore as firestore
    except ImportError as exc:
        raise ImportError(
            "google-cloud-firestore is required. Run: pip install google-cloud-firestore"
        ) from exc

    settings = get_settings()
    project = settings.gcp_project_id or None
    return firestore.Client(project=project)


def get_firestore_async_client() -> Any:
    """Return an authenticated async Firestore client (``firestore.AsyncClient``).

    The workspace/session stores ``await`` their client, so they need the ASYNC
    client — the sync ``Client`` returns non-awaitable snapshots and fails at
    runtime. Raises ImportError if google-cloud-firestore is not installed.
    """
    try:
        import google.cloud.firestore as firestore
    except ImportError as exc:
        raise ImportError(
            "google-cloud-firestore is required. Run: pip install google-cloud-firestore"
        ) from exc

    settings = get_settings()
    project = settings.gcp_project_id or None
    return firestore.AsyncClient(project=project)


def get_secret_manager_client() -> Any:
    """Return an authenticated Secret Manager client (SecretManagerServiceClient).

    Raises ImportError if google-cloud-secret-manager is not installed.
    """
    try:
        import google.cloud.secretmanager as secretmanager
    except ImportError as exc:
        raise ImportError(
            "google-cloud-secret-manager is required. "
            "Run: pip install google-cloud-secret-manager"
        ) from exc

    return secretmanager.SecretManagerServiceClient()


def secret_name_for_user(user_id: str) -> str:
    """Return the Secret Manager secret resource name for a user's BYOK key.

    Format: projects/{project}/secrets/ce-key-{user_id}/versions/latest
    """
    settings = get_settings()
    project = settings.gcp_project_id
    if not project:
        raise OSError("GCP_PROJECT_ID must be set to construct a secret resource name.")
    return f"projects/{project}/secrets/ce-key-{user_id}/versions/latest"
