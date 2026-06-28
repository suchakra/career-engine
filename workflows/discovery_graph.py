"""ADK 2.0 Workflow graph for the CareerEngine discovery loop — Phase 0 stub.

Phase 0 — typed stubs only.  Phase 1 (WS-A) builds the actual graph.

Graph topology (Phase 1):
    START → ingest → [router] → execute_grill_turn | user_checkpoint → finalize → tailor

Router rules (the 5-turn brake):
    - If phase == 'complete' OR active_gaps is empty → finalize_master_resume
    - If question_count > 0 AND question_count % 5 == 0
      AND phase != 'checkpoint' → user_checkpoint_node
    - Otherwise → execute_grill_turn_node

ADK 2.0 wiring notes (ARCHITECTURE.md is structural; real API below):
    - Use google.adk.workflow.Workflow (a subclass of BaseNode) to build the graph.
    - Edges are specified as a list[Edge] passed to Workflow(edges=[...]).
    - Route strings returned by the router function match Edge.route values.
    - FunctionNode(func=..., name=...) wraps each pure node function.
    - The Workflow is passed to Runner(node=workflow, session_service=...).
    - state_schema=CareerEngineState on the Workflow validates state at runtime.

Import paths (verified against google-adk 2.0.0):
    from google.adk.workflow import Workflow, FunctionNode, Edge, START, DEFAULT_ROUTE
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
"""

from __future__ import annotations

from schema import CareerEngineState, PhaseStatus


def discovery_router(state: CareerEngineState) -> str:
    """Route the next step in the discovery graph based on current state.

    Implements the 5-turn checkpoint brake: every 5 questions, force a
    user checkpoint before continuing.

    Args:
        state: Current session state.

    Returns:
        Node name string: one of 'execute_grill_turn_node',
        'user_checkpoint_node', or 'finalize_master_resume_node'.
    """
    if state.current_phase == PhaseStatus.COMPLETE or not state.active_gaps:
        return "finalize_master_resume_node"

    # 5-turn checkpoint brake
    if (
        state.question_count > 0
        and state.question_count % 5 == 0
        and state.current_phase != PhaseStatus.CHECKPOINT
    ):
        return "user_checkpoint_node"

    return "execute_grill_turn_node"


def build_discovery_workflow() -> None:
    """Build and return the ADK 2.0 Workflow for the discovery loop.

    Phase 0 stub — raises NotImplementedError.  Phase 1 (WS-A) builds
    the real Workflow using FunctionNode + Edge objects.

    Returns:
        google.adk.workflow.Workflow instance (Phase 1).

    Raises:
        NotImplementedError: always in Phase 0.
    """
    raise NotImplementedError("build_discovery_workflow is a Phase 1 task.")


def build_runner() -> None:
    """Build and return an ADK 2.0 Runner wired to the discovery workflow.

    Phase 0 stub — raises NotImplementedError.  Phase 1 wires:
        Runner(node=workflow, session_service=session_service)

    Returns:
        google.adk.runners.Runner instance (Phase 1).

    Raises:
        NotImplementedError: always in Phase 0.
    """
    raise NotImplementedError("build_runner is a Phase 1 task.")
