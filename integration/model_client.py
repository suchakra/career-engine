"""Unified Gemini model-client adapter for CareerEngine.

Two different interfaces exist in the codebase and BOTH must be satisfied
by the real google.genai.Client:

1. ``workflows/nodes.py`` uses:
       client.generate(model_id: str, system: str, user: str) -> str
   injected via ``workflows.nodes.set_model_client_factory(factory)``.

2. ``tools/web_scraper.py`` uses:
       client.generate_content_text(*, model: str, system: str, prompt: str) -> str
   passed as the ``client=`` kwarg of ``clean_jd_html`` / ``scrape_job_description``.

``GeminiModelClient`` implements BOTH interfaces over a single ``google.genai.Client``
so callers always see a coherent object regardless of which calling convention
they use.

Access-mode wiring
------------------
``build_model_client(user_id, key_vault, access_mode)`` resolves the API key:

- ``AccessMode.FREE``  → uses ``settings.gemini_api_key`` (platform managed key).
- ``AccessMode.BYOK``  → calls ``key_vault.fetch_key(user_id)`` (Secret Manager).

The function is a factory so the CLI can call it once after auth is resolved
and share the resulting client across all subsystems.

No hardcoded model names live in this module.  The model ID is always passed
in by the caller (resolved via ``models.registry.get_registry().get_model_id()``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from config import AccessMode, get_settings


class ModelAPIError(Exception):
    """A model API call failed (transport / quota / server error).

    Wraps the underlying provider exception so callers (nodes, CLI) can surface a
    friendly message and decide on retry WITHOUT importing google.genai internals.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        is_rate_limited: bool = False,
    ) -> None:
        """Initialise with optional status/retry metadata."""
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.is_rate_limited = is_rate_limited


def _as_model_api_error(exc: Exception) -> ModelAPIError:
    """Translate a provider exception into a typed :class:`ModelAPIError`."""
    code = getattr(exc, "code", None)
    status: int | None = code if isinstance(code, int) else None
    if status is None:
        sc = getattr(exc, "status_code", None)
        status = sc if isinstance(sc, int) else None

    msg = str(exc)
    is_rl = status == 429 or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()

    retry: float | None = None
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", msg) or re.search(
        r"retryDelay['\"]?\s*[:=]\s*['\"]?([0-9]+(?:\.[0-9]+)?)s", msg
    )
    if match:
        try:
            retry = float(match.group(1))
        except ValueError:
            retry = None

    friendly = "Gemini quota / rate limit exceeded" if is_rl else f"Model API call failed: {msg}"
    return ModelAPIError(
        friendly, status_code=status, retry_after_seconds=retry, is_rate_limited=is_rl
    )


@dataclass(frozen=True)
class MediaPart:
    """A single binary media part for a multimodal model call.

    Carries raw bytes plus their MIME type (e.g. ``application/pdf``,
    ``image/png``).  Treated as PII by callers — never persisted to state.
    """

    data: bytes
    mime_type: str


class GeminiModelClient:
    """Unified client adapter satisfying both node and scraper interfaces.

    Wraps a single ``google.genai.Client`` instance and exposes two method
    signatures so that both ``workflows/nodes.py`` and ``tools/web_scraper.py``
    can use the same real client without code duplication.

    Args:
        api_key: Gemini API key to use for all inference calls.  Pass ``None``
            to let the SDK resolve credentials from the environment (ADC).
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialise the underlying google.genai.Client.

        Args:
            api_key: Optional Gemini API key.  When ``None``, the SDK uses
                Application Default Credentials.
        """
        import google.genai as genai

        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    # ── Interface 1: nodes.py convention ─────────────────────────────────────

    def generate(self, model_id: str, system: str, user: str) -> str:
        """Generate text using positional (model_id, system, user) args.

        This is the interface expected by ``workflows/nodes.py``.  The model
        ID must be passed in (resolved by the caller via the registry — never
        hardcoded here).

        Args:
            model_id: Model identifier resolved from the capability registry.
            system: System instruction for the model.
            user: User-turn text.

        Returns:
            The model's plain-text response (empty string only when the model
            genuinely returns no text).

        Raises:
            ModelAPIError: transport / API errors (quota, 429, server) are wrapped
                and propagated rather than swallowed into ``""`` (REVIEW.md #4).  A
                hard failure masquerading as weak model output hides real outages;
                the node/runner/CLI layer decides how to surface it.
        """
        from google.genai import types as gtypes

        try:
            response = self._client.models.generate_content(
                model=model_id,
                contents=user,
                config=gtypes.GenerateContentConfig(system_instruction=system),
            )
        except Exception as exc:
            raise _as_model_api_error(exc) from exc
        return response.text or ""

    # ── Multimodal entry point (Phase 1.5 / vision ingest) ────────────────────

    def generate_multimodal(
        self,
        *,
        model_id: str,
        system: str,
        prompt: str,
        media: Sequence[MediaPart],
    ) -> str:
        """Generate text from a text prompt plus one or more binary media parts.

        Gemini is natively multimodal, so PDF and image bytes are sent directly
        as inline parts (no local OCR / rasterization pipeline).  Used by the
        vision resume parser (``tools/resume_parser.py``).

        Args:
            model_id: Model identifier resolved from the capability registry.
            system: System instruction for the model.
            prompt: The text-turn instruction accompanying the media.
            media: Binary parts (PDF/image bytes + MIME type).  Treated as PII;
                this method does not persist them.

        Returns:
            The model's plain-text response (empty string only when the model
            genuinely returns no text).

        Raises:
            ModelAPIError: transport / API errors are wrapped and propagated
                rather than swallowed (mirrors :meth:`generate`).
        """
        from google.genai import types as gtypes

        parts: list[Any] = [
            gtypes.Part.from_bytes(data=m.data, mime_type=m.mime_type) for m in media
        ]
        parts.append(gtypes.Part.from_text(text=prompt))
        try:
            response = self._client.models.generate_content(
                model=model_id,
                contents=parts,
                config=gtypes.GenerateContentConfig(system_instruction=system),
            )
        except Exception as exc:
            raise _as_model_api_error(exc) from exc
        return response.text or ""

    # ── Interface 2: web_scraper.py convention ────────────────────────────────

    def generate_content_text(self, *, model: str, system: str, prompt: str) -> str:
        """Generate text using keyword (model, system, prompt) args.

        This is the interface expected by ``tools/web_scraper.py``.  The
        method name and signature match what ``_GenAIClientProtocol`` in the
        scraper module declares.

        Args:
            model: Model identifier (keyword-only).
            system: System instruction (keyword-only).
            prompt: User-turn text (keyword-only).

        Returns:
            The model's plain-text response.

        Raises:
            ScraperError: if the model call fails or returns an empty response.
        """
        from google.genai import types as gtypes

        from tools.web_scraper import ScraperError

        try:
            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(system_instruction=system),
            )
        except Exception as exc:
            raise ScraperError(f"Model call failed: {exc}") from exc

        text = response.text
        if not text:
            raise ScraperError("Model returned an empty response for JD cleaning.")
        return text

    # ── Internal helper ───────────────────────────────────────────────────────

    @property
    def raw_client(self) -> Any:
        """Expose the underlying google.genai.Client (for advanced callers)."""
        return self._client


def build_model_client(
    *,
    user_id: str,
    key_vault: Any,
    access_mode: AccessMode,
) -> GeminiModelClient:
    """Construct a GeminiModelClient using the correct API key for the access mode.

    Access-mode key resolution:
    - ``FREE``  → ``settings.gemini_api_key`` (platform-managed; may be empty
      in offline dev, in which case the SDK uses ADC / no key).
    - ``BYOK``  → ``key_vault.fetch_key(user_id)`` from Secret Manager.

    Args:
        user_id: The authenticated user's stable platform ID.
        key_vault: A ``KeyVault`` instance (e.g. ``SecretManagerKeyVault``).
        access_mode: ``AccessMode.FREE`` or ``AccessMode.BYOK``.

    Returns:
        A fully initialised ``GeminiModelClient`` ready for use.

    Raises:
        KeyVaultError: if BYOK mode is requested but no key is stored for the
            user.
    """
    settings = get_settings()

    if access_mode == AccessMode.BYOK:
        api_key: str | None = key_vault.fetch_key(user_id)
    else:
        # FREE mode: use platform-managed key; fall through to ADC if unset.
        api_key = settings.gemini_api_key or settings.dev_gemini_key or None

    return GeminiModelClient(api_key=api_key)
