"""ADK 2.0 Workflow graph for the CareerEngine discovery loop — Phase 1 (WS-A).

Graph topology:
    START → ingest → [discovery_router] → execute_grill_turn
                                        → user_checkpoint
                                        → finalize_master_resume → tailor

Router rules (the 5-turn brake — FROZEN in Phase 0):
    - If phase == 'complete' OR active_gaps is empty → finalize_master_resume_node
    - If question_count > 0 AND question_count % 5 == 0
      AND phase != 'checkpoint' → user_checkpoint_node
    - Otherwise → execute_grill_turn_node

ADK 2.0 wiring notes (verified against google-adk==2.0.0):
    - Workflow(edges=[...]) builds the graph from Edge objects.
    - Edge(from_node=<BaseNode>, to_node=<BaseNode>, route=<str>) — note:
      from_node and to_node are BaseNode instances, NOT strings.
    - FunctionNode(func=..., name=...) wraps a Python callable.
    - When parameter_binding='state' (default), the function receives individual
      kwargs looked up by NAME from ctx.state (a dict-like State object).
      The Workflow._validate_state_schema() checks that every function parameter
      name matches a field in state_schema — so if state_schema is set, each
      parameter must be a CareerEngineState field name.
    - We use ctx-receiving functions instead: a function that accepts 'ctx'
      receives the full InvocationContext, bypassing the field-name constraint.
      This lets us marshal the whole CareerEngineState at the boundary.
    - Runner(node=workflow, session_service=..., app_name=...) — app_name must
      match the app_name used in session_service.create_session().
    - START is a module-level BaseNode sentinel; DEFAULT_ROUTE == "__DEFAULT__".

State marshalling contract:
    Each ADK-wrapped function (shim) does:
      1. Read all CareerEngineState fields from ctx.state (stored flat as a dict).
      2. Construct a CareerEngineState from them.
      3. Call the corresponding pure node function.
      4. Write the returned state's fields back into ctx.state.
    This keeps the pure functions in nodes.py fully decoupled from ADK.
"""

from __future__ import annotations

from typing import Any, cast

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.workflow import DEFAULT_ROUTE, START, Edge, FunctionNode, Workflow

from schema import CareerEngineState, PhaseStatus
from workflows.nodes import (
    execute_grill_turn_node,
    finalize_master_resume_node,
    ingest_node,
    tailor_node,
    user_checkpoint_node,
)

# ── Router (FROZEN Phase-0 contract) ─────────────────────────────────────────


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


# ── State marshalling helpers ─────────────────────────────────────────────────


def _read_state(ctx: object) -> CareerEngineState:
    """Read CareerEngineState from ADK ctx.state (flat dict → Pydantic model)."""
    # ctx.state is a State object (dict-like); model_validate handles missing fields
    # by using defaults defined in CareerEngineState.
    raw: dict[object, object] = {}
    state_obj = getattr(ctx, "state", {})
    for field in CareerEngineState.model_fields:
        if field in state_obj:
            raw[field] = state_obj[field]
    return CareerEngineState.model_validate(raw)


def _write_state(ctx: object, new_state: CareerEngineState) -> None:
    """Write CareerEngineState fields back into ADK ctx.state."""
    state_obj = getattr(ctx, "state", {})
    for field, value in new_state.model_dump().items():
        state_obj[field] = value


# ── ADK shims (ctx-receiving wrappers around the pure node functions) ─────────


def _ingest_shim(ctx: object) -> None:
    """ADK shim: reads state from ctx, calls ingest_node, writes result back."""
    state = _read_state(ctx)
    new_state = ingest_node(state)
    _write_state(ctx, new_state)


def _router_shim(ctx: object) -> None:
    """ADK shim: reads state from ctx, calls discovery_router, sets ctx.route.

    INTEGRATION NOTE: FunctionNode wraps a plain str return value as
    Event(output=...), which lands in child_ctx.output — NOT in child_ctx.route.
    The ADK Workflow's _buffer_downstream_triggers uses child_ctx.route to
    select the matching Edge, so a string return value causes all router
    branches to be silently skipped (falls back to DEFAULT_ROUTE only, which
    doesn't exist for the router → the graph terminates after ingest).

    Setting ctx.route directly writes to ctx._route_value, which
    _flush_output_and_deltas then emits as Event(route=...) → tracked by
    _track_event_in_context as ctx.route → used by _buffer_downstream_triggers.
    This is the correct ADK 2.0 pattern for routing FunctionNodes.
    """
    state = _read_state(ctx)
    route = discovery_router(state)
    # Set route on the context object; ADK flushes it as Event(route=...) so
    # _buffer_downstream_triggers can select the correct outgoing edge.
    setattr(ctx, "route", route)  # ctx is the ADK Context; mypy sees 'object'


def _grill_shim(ctx: object) -> None:
    """ADK shim: reads state, calls execute_grill_turn_node, writes result back.

    If the node returns UpgradeRequired, stores the signal in ctx.state so the
    runner can surface it to the UI without crashing.
    """
    from schema import UpgradeRequired

    state = _read_state(ctx)
    result = execute_grill_turn_node(state)
    if isinstance(result, UpgradeRequired):
        # Store the typed signal; the UI/CLI layer inspects this key
        state_obj = getattr(ctx, "state", {})
        state_obj["_upgrade_required"] = result.model_dump_json()
    else:
        _write_state(ctx, result)


def _checkpoint_shim(ctx: object) -> None:
    """ADK shim: reads state, calls user_checkpoint_node, writes result back."""
    state = _read_state(ctx)
    new_state = user_checkpoint_node(state)
    _write_state(ctx, new_state)


def _finalize_shim(ctx: object) -> None:
    """ADK shim: reads state, calls finalize_master_resume_node, writes result back."""
    state = _read_state(ctx)
    new_state = finalize_master_resume_node(state)
    _write_state(ctx, new_state)


def _tailor_shim(ctx: object) -> None:
    """ADK shim: reads state, calls tailor_node, writes result back."""
    state = _read_state(ctx)
    new_state = tailor_node(state)
    _write_state(ctx, new_state)


# ── Workflow builder ──────────────────────────────────────────────────────────


def build_discovery_workflow() -> Workflow:
    """Build and return the ADK 2.0 Workflow for the discovery loop.

    Graph:
        START → ingest → router → execute_grill_turn
                               → user_checkpoint
                               → finalize_master_resume → tailor

    Returns:
        google.adk.workflow.Workflow instance ready to be passed to a Runner.
    """
    # ── Create FunctionNode instances ─────────────────────────────────────────
    ingest = FunctionNode(func=_ingest_shim, name="ingest_node")
    router = FunctionNode(func=_router_shim, name="discovery_router")
    grill = FunctionNode(func=_grill_shim, name="execute_grill_turn_node")
    checkpoint = FunctionNode(func=_checkpoint_shim, name="user_checkpoint_node")
    finalize = FunctionNode(func=_finalize_shim, name="finalize_master_resume_node")
    tailor = FunctionNode(func=_tailor_shim, name="tailor_node")

    # ── Wire edges ────────────────────────────────────────────────────────────
    # Route strings set on ctx.route by _router_shim must match Edge.route values.
    edges: list[Edge] = [
        # Entry: START → ingest
        Edge(from_node=START, to_node=ingest, route=DEFAULT_ROUTE),
        # After ingest → router
        Edge(from_node=ingest, to_node=router, route=DEFAULT_ROUTE),
        # Router branches (route strings match discovery_router return values)
        Edge(from_node=router, to_node=grill, route="execute_grill_turn_node"),
        Edge(from_node=router, to_node=checkpoint, route="user_checkpoint_node"),
        Edge(from_node=router, to_node=finalize, route="finalize_master_resume_node"),
        # After grill → back to router (loop)
        Edge(from_node=grill, to_node=router, route=DEFAULT_ROUTE),
        # After checkpoint → back to router (loop — router will branch based on
        # checkpoint_verified; the CLI sets checkpoint_verified=True before resuming)
        Edge(from_node=checkpoint, to_node=router, route=DEFAULT_ROUTE),
        # After finalize → tailor
        Edge(from_node=finalize, to_node=tailor, route=DEFAULT_ROUTE),
        # tailor is terminal (no outgoing edges)
    ]

    # Workflow's `edges` parameter is typed as an invariant list of a broad
    # union (Edge | tuple | dict ...).  Our list is homogeneous list[Edge];
    # cast to satisfy the invariant signature without widening our own type.
    return Workflow(
        name="career_engine_discovery",
        edges=cast("list[Any]", edges),
        # Note: state_schema is intentionally NOT set on the Workflow because
        # our shim functions accept 'ctx' (bypassing _validate_state_schema).
        # State contract validation happens inside _read_state()/_write_state().
    )


def build_runner(
    session_service: BaseSessionService | None = None,
    app_name: str = "career_engine_discovery",
) -> Runner:
    """Build and return an ADK 2.0 Runner wired to the discovery workflow.

    Args:
        session_service: ADK session service to use.  Defaults to
            InMemorySessionService (for testing).  Production wires in
            FirestoreSessionService (WS-C).
        app_name: Application name; must match the name used in
            session_service.create_session().

    Returns:
        google.adk.runners.Runner instance ready to call run_async().
    """
    if session_service is None:
        # InMemorySessionService is an untyped ADK constructor; the cast keeps
        # the typed BaseSessionService contract for downstream code.
        session_service = cast(
            "BaseSessionService",
            InMemorySessionService(),  # type: ignore[no-untyped-call]
        )

    workflow = build_discovery_workflow()
    return Runner(
        node=workflow,
        session_service=session_service,
        app_name=app_name,
    )
