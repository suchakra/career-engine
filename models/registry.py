"""Capability → model resolver interface and Free/BYOK routing stubs.

Phase 0 — stub bodies only.  No real model calls are made here.
Phase 1 will fill in _resolve_free_model() and _resolve_byok_model() with real
model IDs sourced from a config table — never hardcoded in feature code.

Design rules:
- No feature code ever names a model string.  Features call get_model_id().
- Model IDs live in MODEL_MAP constants defined in THIS file only.
- Free Mode is "fully functional out of the box" (decision D2): it resolves
  ALL three capabilities to a real model.  REASONING_HIGH is served on the
  Flash + Chain-of-Thought baseline (decision D3 / ARCHITECTURE.md §6.4), not
  refused.
- BYOK Mode: user key from Secret Manager; REASONING_HIGH routes to Pro for a
  higher reasoning ceiling.
- UpgradeRequired is NOT emitted by the resolver for the baseline.  It is a
  NODE-LEVEL validation-gate signal (ARCHITECTURE.md §6.3 trigger (a)): a node
  returns it only after Flash+CoT genuinely fails to extract a metric in Free
  Mode.  The `str | UpgradeRequired` return type is retained because that is
  the typed signal nodes use; the resolver itself does not refuse the baseline.

ADK 2.0 deviation note:
    ARCHITECTURE.md referenced a generic "BaseAgent" style for the resolver.
    The real google.adk 2.0 package exposes model selection via the `model`
    parameter on LlmAgent (a string or google.genai model name).  The registry
    here acts as the single source of truth that vends those strings; no other
    module is permitted to reference model names directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from config import AccessMode, get_settings
from schema import Capability, UpgradeRequired

# ── Model name constants (ONLY place model strings are allowed in the codebase) ──

# Free Mode: all three capabilities resolve to a real free-tier model.
# REASONING_HIGH is served on Flash + Chain-of-Thought (the baseline path);
# the node's validation gate — not this resolver — emits UpgradeRequired if
# Flash+CoT cannot extract a metric.
_FREE_MODEL_MAP: dict[Capability, str] = {
    Capability.REASONING_HIGH: "gemini-2.5-flash",
    Capability.SPEED_FAST: "gemini-2.5-flash",
    Capability.BULK_CHEAP: "gemini-2.5-flash-lite",
}

# BYOK Mode: user's key grants access to all models; REASONING_HIGH routes to
# Pro for a higher reasoning ceiling.
_BYOK_MODEL_MAP: dict[Capability, str] = {
    Capability.REASONING_HIGH: "gemini-2.5-pro",
    Capability.SPEED_FAST: "gemini-2.5-flash",
    Capability.BULK_CHEAP: "gemini-2.5-flash-lite",
}


# ── Abstract interface ────────────────────────────────────────────────────────


class BaseModelRegistry(ABC):
    """Abstract registry interface — Phase 1 provides concrete implementations."""

    @abstractmethod
    def get_model_id(
        self,
        capability: Capability,
        *,
        access_mode: AccessMode | None = None,
    ) -> str | UpgradeRequired:
        """Resolve a capability to a model identifier for the current access mode.

        Returns a model ID string on success, or UpgradeRequired if the
        capability cannot be satisfied for the given access mode.
        """
        ...

    @abstractmethod
    def supports(self, capability: Capability, *, access_mode: AccessMode) -> bool:
        """Return True if the given capability is satisfiable in the given access mode."""
        ...


# ── Default implementation (stub for Phase 0) ─────────────────────────────────


class DefaultModelRegistry(BaseModelRegistry):
    """Default capability registry with Free/BYOK routing.

    Phase 0: routing logic is present; model ID strings are sourced from the
    constant maps above.  Phase 1 may extend this class to add capability
    detection, quota tracking, and per-user overrides.
    """

    def get_model_id(
        self,
        capability: Capability,
        *,
        access_mode: AccessMode | None = None,
    ) -> str | UpgradeRequired:
        """Return a model ID for the requested capability and access mode.

        Free Mode resolves every capability to a real model (REASONING_HIGH on
        Flash + Chain-of-Thought).  BYOK Mode routes REASONING_HIGH to Pro.
        The resolver never refuses the baseline; UpgradeRequired is a node-level
        validation-gate signal emitted only after Flash+CoT fails to extract a
        metric.  The defensive branch below returns UpgradeRequired only if a
        capability is genuinely unmapped (a config error, not the baseline path).
        """
        mode = access_mode or get_settings().access_mode
        model_map = _BYOK_MODEL_MAP if mode == AccessMode.BYOK else _FREE_MODEL_MAP

        if capability in model_map:
            return model_map[capability]

        # Capability is unmapped for this mode — a configuration error, not the
        # normal grilling baseline.  Surface a typed signal rather than KeyError.
        return UpgradeRequired(
            required_capability=capability,
            node_name="DefaultModelRegistry",
            reason=(
                f"Capability {capability.value!r} has no model mapping in "
                f"{mode.value} mode."
            ),
        )

    def supports(self, capability: Capability, *, access_mode: AccessMode) -> bool:
        """Return True if the capability resolves to a real model in the given mode."""
        if access_mode == AccessMode.BYOK:
            return capability in _BYOK_MODEL_MAP
        return capability in _FREE_MODEL_MAP


# ── Module-level singleton ────────────────────────────────────────────────────

_registry: BaseModelRegistry = DefaultModelRegistry()


def get_registry() -> BaseModelRegistry:
    """Return the application model registry singleton."""
    return _registry


def set_registry(registry: BaseModelRegistry) -> None:
    """Replace the registry singleton (for testing or Phase 1 wiring)."""
    global _registry
    _registry = registry
