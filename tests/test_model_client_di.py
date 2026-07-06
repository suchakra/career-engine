"""Tests for explicit DI model-client isolation (WS 8D).

Acceptance criteria:
- test_di_node_uses_explicit_client: node uses _client= over module factory
- test_di_node_fallback_to_module_factory: node falls back to module factory when no _client
- test_di_two_workflows_isolated: two build_discovery_workflow instances don't bleed clients
- test_build_runner_threads_factory: build_runner(model_factory=...) calls the factory
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from google.adk.sessions import InMemorySessionService

from schema import (
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    PhaseStatus,
)
from workflows import nodes as _nodes_module
from workflows.discovery_graph import build_runner
from workflows.nodes import (
    execute_grill_turn_node,
    set_model_client_factory,
)

# ── Test doubles ──────────────────────────────────────────────────────────────


class _SentinelClient:
    """Minimal ModelClient stand-in that records calls and returns valid JSON."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict[str, str]] = []

    def generate(self, model_id: str, system: str, user: str) -> str:
        self.calls.append({"model_id": model_id, "system": system, "user": user})
        # Return a minimal valid grill-turn JSON so the node doesn't fail.
        import json as _json

        return _json.dumps(
            {
                "situation": "s",
                "task": "t",
                "action": "a",
                "result": "increased revenue by 20%",
                "metrics_found": True,
                "metric_summary": "20%",
            }
        )


def _grilling_state() -> CareerEngineState:
    """Return a CareerEngineState ready for a grill turn."""
    entry = Entry(
        type=ExperienceType.FULL_TIME,
        title="Senior Engineer",
        org="Acme",
        start_date="2023",
        end_date="2024",
        status=EntryStatus.NEEDS_QUANTIFYING,
    )
    return CareerEngineState(
        current_phase=PhaseStatus.GRILLING,
        work_timeline=[entry],
        grill_frontier=str(entry.entry_id),
        pending_user_answer="We cut p99 latency from 800 ms to 120 ms.",
        question_count=1,
        reference_date="2026-07-06",
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_factory() -> object:
    """Restore the module-level client factory after each test."""
    original = _nodes_module._client_factory
    yield
    _nodes_module._client_factory = original


@pytest.fixture(autouse=True)
def _force_byok_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use BYOK access mode so REASONING_HIGH resolves to a real model id."""
    from config import AccessMode, Settings
    from models.registry import DefaultModelRegistry, set_registry

    set_registry(DefaultModelRegistry())
    monkeypatch.setattr(
        _nodes_module,
        "get_settings",
        lambda: Settings(access_mode=AccessMode.BYOK),
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestDINodeUsesExplicitClient:
    """test_di_node_uses_explicit_client: _client= takes precedence over the module factory."""

    def test_di_node_uses_explicit_client(self) -> None:
        explicit_client = _SentinelClient("explicit")
        factory_client = _SentinelClient("factory")

        set_model_client_factory(lambda: factory_client)

        state = _grilling_state()
        execute_grill_turn_node(state, _client=explicit_client)

        assert explicit_client.calls, "explicit client was not called"
        assert not factory_client.calls, "factory client was called — bleed detected"


class TestDINodeFallbackToModuleFactory:
    """test_di_node_fallback_to_module_factory: without _client=, falls back to module factory."""

    def test_di_node_fallback_to_module_factory(self) -> None:
        factory_client = _SentinelClient("factory_fallback")
        set_model_client_factory(lambda: factory_client)

        state = _grilling_state()
        execute_grill_turn_node(state)  # no _client= passed

        assert factory_client.calls, "factory client was not called — fallback broken"


class TestDITwoWorkflowsIsolated:
    """test_di_two_workflows_isolated: two Workflow instances use separate clients."""

    def _run_one_grill_turn(
        self,
        client: _SentinelClient,
    ) -> None:
        """Run one grill turn through a dedicated runner to verify client isolation."""
        svc: Any = InMemorySessionService()  # type: ignore[no-untyped-call]
        session_id = str(uuid.uuid4())
        app_name = "test_isolation"
        user_id = "test_user"

        state = _grilling_state()

        async def _run() -> None:
            await svc.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=state.model_dump(mode="json"),
            )
            runner = build_runner(
                session_service=svc,
                app_name=app_name,
                model_factory=lambda: client,
            )
            async for _ in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                state_delta={},
            ):
                pass

        asyncio.run(_run())

    def test_di_two_workflows_isolated(self) -> None:
        client_a = _SentinelClient("A")
        client_b = _SentinelClient("B")

        # Run workflow A with client_a factory only.
        self._run_one_grill_turn(client_a)
        calls_a_after_first = len(client_a.calls)
        calls_b_after_first = len(client_b.calls)

        assert calls_a_after_first > 0, "client_a was not called during its own run"
        assert calls_b_after_first == 0, (
            f"client_b was called {calls_b_after_first} time(s) during client_a's run — bleed!"
        )

        # Run workflow B with client_b factory only.
        self._run_one_grill_turn(client_b)

        assert len(client_b.calls) > 0, "client_b was not called during its own run"
        assert len(client_a.calls) == calls_a_after_first, (
            "client_a accumulated more calls during client_b's run — bleed!"
        )


class TestBuildRunnerThreadsFactory:
    """test_build_runner_threads_factory: build_runner passes model_factory through."""

    def test_build_runner_threads_factory(self) -> None:
        fake_client = _SentinelClient("runner_factory")
        call_count: list[int] = [0]

        def fake_factory() -> _SentinelClient:
            call_count[0] += 1
            return fake_client

        svc: Any = InMemorySessionService()  # type: ignore[no-untyped-call]
        session_id = str(uuid.uuid4())
        app_name = "test_runner_factory"
        user_id = "test_user"

        state = _grilling_state()

        async def _run() -> None:
            await svc.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=state.model_dump(mode="json"),
            )
            runner = build_runner(
                session_service=svc,
                app_name=app_name,
                model_factory=fake_factory,
            )
            async for _ in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                state_delta={},
            ):
                pass

        asyncio.run(_run())

        assert call_count[0] > 0, "fake_factory was never called by the runner"
        assert fake_client.calls, "fake_client.generate was never called"


class TestBuildRunnerThreadsTailorInstructions:
    """test_build_runner_threads_tailor_instructions: tailor_instructions flows into tailor_node."""

    def test_build_runner_threads_tailor_instructions(self) -> None:
        fake_client = _SentinelClient("tailor_instructions_test")

        svc: Any = InMemorySessionService()  # type: ignore[no-untyped-call]
        session_id = str(uuid.uuid4())
        app_name = "test_tailor_instructions"
        user_id = "test_user"

        # Phase=COMPLETE so router → finalize → tailor runs in one pass.
        state = CareerEngineState(
            current_phase=PhaseStatus.COMPLETE,
            master_resume_json='{"summary": "test"}',
            jd_text="Build distributed systems.",
            reference_date="2026-07-06",
        )

        async def _run() -> None:
            await svc.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=state.model_dump(mode="json"),
            )
            runner = build_runner(
                session_service=svc,
                app_name=app_name,
                model_factory=lambda: fake_client,
                tailor_instructions="be concise",
            )
            async for _ in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                state_delta={},
            ):
                pass

        asyncio.run(_run())

        # tailor_node is the last node; its generate() call carries the instructions.
        assert fake_client.calls, "client was never called"
        tailor_call = fake_client.calls[-1]
        assert "be concise" in tailor_call["system"], (
            f"tailor_instructions not found in system prompt: {tailor_call['system']!r}"
        )
