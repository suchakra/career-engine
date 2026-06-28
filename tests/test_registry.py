"""Behavior tests for the capability → model registry.

Verifies the Free/BYOK routing policy (decisions D2/D3, ARCHITECTURE.md §6.2/§6.4):
- Free Mode is fully functional: every capability resolves to a real model string.
- REASONING_HIGH in Free Mode is served on Flash + Chain-of-Thought (NOT refused).
- BYOK Mode routes REASONING_HIGH to Pro for a higher reasoning ceiling.
- UpgradeRequired is a node-level signal, not a resolver refusal for the baseline.
"""

from __future__ import annotations

from config import AccessMode
from models.registry import DefaultModelRegistry
from schema import Capability


class TestFreeModeRouting:
    """Free Mode must resolve all three capabilities to real model strings."""

    def test_reasoning_high_returns_flash_not_upgrade(self) -> None:
        """Free-mode REASONING_HIGH resolves to gemini-2.5-flash (a str, NOT UpgradeRequired)."""
        registry = DefaultModelRegistry()
        result = registry.get_model_id(Capability.REASONING_HIGH, access_mode=AccessMode.FREE)
        assert isinstance(result, str)
        assert result == "gemini-2.5-flash"

    def test_speed_fast_resolves(self) -> None:
        """Free-mode SPEED_FAST resolves to gemini-2.5-flash."""
        registry = DefaultModelRegistry()
        result = registry.get_model_id(Capability.SPEED_FAST, access_mode=AccessMode.FREE)
        assert result == "gemini-2.5-flash"

    def test_bulk_cheap_resolves(self) -> None:
        """Free-mode BULK_CHEAP resolves to gemini-2.5-flash-lite."""
        registry = DefaultModelRegistry()
        result = registry.get_model_id(Capability.BULK_CHEAP, access_mode=AccessMode.FREE)
        assert result == "gemini-2.5-flash-lite"

    def test_all_capabilities_resolve_to_str(self) -> None:
        """Free Mode never returns UpgradeRequired for any defined capability."""
        registry = DefaultModelRegistry()
        for cap in Capability:
            result = registry.get_model_id(cap, access_mode=AccessMode.FREE)
            assert isinstance(result, str), f"Free Mode refused {cap.value}"


class TestByokModeRouting:
    """BYOK Mode must route REASONING_HIGH to Pro and others to Flash tiers."""

    def test_reasoning_high_returns_pro(self) -> None:
        """BYOK REASONING_HIGH resolves to gemini-2.5-pro."""
        registry = DefaultModelRegistry()
        result = registry.get_model_id(Capability.REASONING_HIGH, access_mode=AccessMode.BYOK)
        assert result == "gemini-2.5-pro"

    def test_speed_fast_resolves(self) -> None:
        """BYOK SPEED_FAST resolves to gemini-2.5-flash."""
        registry = DefaultModelRegistry()
        result = registry.get_model_id(Capability.SPEED_FAST, access_mode=AccessMode.BYOK)
        assert result == "gemini-2.5-flash"

    def test_bulk_cheap_resolves(self) -> None:
        """BYOK BULK_CHEAP resolves to gemini-2.5-flash-lite."""
        registry = DefaultModelRegistry()
        result = registry.get_model_id(Capability.BULK_CHEAP, access_mode=AccessMode.BYOK)
        assert result == "gemini-2.5-flash-lite"


class TestSupports:
    """supports() must reflect that both modes satisfy all three capabilities."""

    def test_free_mode_supports_all(self) -> None:
        """Free Mode supports all three capabilities, including REASONING_HIGH."""
        registry = DefaultModelRegistry()
        for cap in Capability:
            assert registry.supports(cap, access_mode=AccessMode.FREE), (
                f"Free Mode should support {cap.value}"
            )

    def test_byok_mode_supports_all(self) -> None:
        """BYOK Mode supports all three capabilities."""
        registry = DefaultModelRegistry()
        for cap in Capability:
            assert registry.supports(cap, access_mode=AccessMode.BYOK), (
                f"BYOK Mode should support {cap.value}"
            )

    def test_free_mode_supports_reasoning_high(self) -> None:
        """Explicit: Free Mode supports REASONING_HIGH (the grilling baseline)."""
        registry = DefaultModelRegistry()
        assert registry.supports(Capability.REASONING_HIGH, access_mode=AccessMode.FREE) is True
