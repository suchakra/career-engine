"""ADK 2.0 Workflow graph for the CareerEngine discovery loop — Phase 1.5.

Graph topology:
    START → ingest → [discovery_router] → execute_grill_turn
                                        → user_checkpoint
                                        → finalize_master_resume → tailor

Router rules (the 5-turn brake — unchanged behavior):
    - If phase == 'complete' OR no entries need work → finalize_master_resume_node
    - If question_count > 0 AND question_count % 5 == 0
      AND phase != 'checkpoint' → user_checkpoint_node
    - Otherwise → execute_grill_turn_node

v2.0.0 changes:
    - Router uses work_timeline (instead of active_gaps) to determine if grilling
      is needed.  "No active work" = no NEEDS_QUANTIFYING or DOCUMENTED entries.
    - Shims updated to work with Entry-based state.
    - discovery_turn_node added as an optional node (not yet in the main graph;
      the 1.5-DISCOVERY workstream wires it into the CLI flow).

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

from collections.abc import Callable
from typing import Any, cast

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.workflow import DEFAULT_ROUTE, START, Edge, FunctionNode, Workflow

from schema import CareerEngineState, EntryStatus, PhaseStatus
from workflows.nodes import (
    ModelClient,
    discovery_turn_node,
    execute_grill_turn_node,
    finalize_master_resume_node,
    ingest_node,
    tailor_node,
    user_checkpoint_node,
)

# ── Router (adapted for v2.0.0 entry-based state) ─────────────────────────────


def _has_pending_work(state: CareerEngineState) -> bool:
    """Return True if any entries in the work_timeline still need grilling."""
    return any(
        e.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED)
        for e in state.work_timeline
    )


def discovery_router(state: CareerEngineState) -> str:
    """Route the next step in the discovery graph based on current state.

    Implements the 5-turn checkpoint brake: every 5 questions, force a
    user checkpoint before continuing.

    v2.0.0: uses work_timeline to determine if grilling is needed.
    "No pending work" = all entries are grilled/summarized/skipped.

    Turn-based / human-in-the-loop note:
        Each ``runner.run_async`` invocation advances the workflow by exactly
        ONE work node (grill, checkpoint, or finalize→tailor) and then the
        graph terminates, returning control to the CLI which collects the next
        human input (a new ``pending_user_answer`` or ``checkpoint_verified``).
        This router therefore selects the single node to run THIS turn; it does
        not loop.  The grill and checkpoint nodes are terminal within a turn
        (no back-edge to the router) so the run cannot spin without new input.

        A verified checkpoint (``checkpoint_verified=True``) is resolved at the
        graph entry (``_ingest_shim``) which advances the phase back to GRILLING
        BEFORE this router runs, so the frozen rule below — "suppress the brake
        while phase==CHECKPOINT" — keeps holding without re-triggering the
        checkpoint node.

    Routing rules (v2.1.0 — entry-based, with the one-shot discovery turn):
        - phase == COMPLETE → finalize_master_resume_node.
        - pending work: 5-turn brake (question_count > 0, multiple of 5, phase
          NOT already CHECKPOINT) → user_checkpoint_node; otherwise →
          execute_grill_turn_node.
        - no pending work: if there is a coverage boundary to confirm
          (coverage_through set), it is unconfirmed, and we are not paused at a
          checkpoint → discovery_turn_node (once); otherwise →
          finalize_master_resume_node.

    Args:
        state: Current session state.

    Returns:
        Node name string: one of 'execute_grill_turn_node',
        'user_checkpoint_node', 'discovery_turn_node', or
        'finalize_master_resume_node'.
    """
    if state.current_phase == PhaseStatus.COMPLETE:
        return "finalize_master_resume_node"

    if not _has_pending_work(state):
        # No entries need grilling.  Before finalizing, run the one-shot discovery
        # turn IF there is a coverage boundary to confirm (coverage_through set by
        # a resume ingest) and it has not been confirmed yet.  This surfaces the
        # "your resume runs through X — what have you done since?" turn.  Skipped
        # for present-role / text sessions (coverage_through empty) and once the
        # user has answered (coverage_confirmed).  Suppressed during CHECKPOINT.
        if (
            state.coverage_through
            and not state.coverage_confirmed
            and state.current_phase != PhaseStatus.CHECKPOINT
        ):
            return "discovery_turn_node"
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


# ── Workflow builder ──────────────────────────────────────────────────────────
# NOTE: The ADK shim functions (ctx-receiving wrappers) are defined as closures
# inside build_discovery_workflow() so that each workflow instance can capture
# its own model_factory for per-runner client isolation (8D DI fix).  There are
# NO module-level shim functions — using closures is the only safe pattern.


def build_discovery_workflow(
    model_factory: Callable[[], ModelClient] | None = None,
    tailor_instructions: str = "",
) -> Workflow:
    """Build and return the ADK 2.0 Workflow for the discovery loop.

    Args:
        model_factory: Optional callable that returns a ModelClient.  When
            supplied, every shim passes the result as ``_client=`` to its node
            so each workflow instance is isolated from the process-global
            factory.  When ``None``, nodes fall back to ``_get_model_client()``
            (CLI / test path).
        tailor_instructions: Optional per-application instructions forwarded
            to ``tailor_node`` as ``_instructions``.  Appended to the *user*
            prompt (not the system prompt) so the fixed system rules remain
            intact.  Defaults to ``""`` (no extra instructions).

    Graph:
        START → ingest → router → execute_grill_turn
                               → user_checkpoint
                               → finalize_master_resume → tailor

    Returns:
        google.adk.workflow.Workflow instance ready to be passed to a Runner.
    """
    # ── Closure shims — capture model_factory per workflow instance ───────────
    def _ci_ingest_shim(ctx: object) -> None:
        """Entry shim: idempotent ingest + checkpoint resolution."""
        state = _read_state(ctx)
        _c = model_factory() if model_factory is not None else None
        if state.current_phase == PhaseStatus.INGESTING:
            state = ingest_node(state, _client=_c)
            _write_state(ctx, state)
        elif (
            state.current_phase == PhaseStatus.CHECKPOINT and state.checkpoint_verified
        ):
            state = user_checkpoint_node(state, _client=_c)
            state = state.model_copy(
                update={"question_count": state.question_count + 1}
            )
            _write_state(ctx, state)

    def _ci_router_shim(ctx: object) -> None:
        """Router shim: no model call; sets ctx.route."""
        state = _read_state(ctx)
        route = discovery_router(state)
        cast("Any", ctx).route = route

    def _ci_grill_shim(ctx: object) -> None:
        """Grill shim: passes explicit client when model_factory is set."""
        from schema import UpgradeRequired

        state = _read_state(ctx)
        _c = model_factory() if model_factory is not None else None
        result = execute_grill_turn_node(state, _client=_c)
        if isinstance(result, UpgradeRequired):
            state_obj = getattr(ctx, "state", {})
            state_obj["_upgrade_required"] = result.model_dump_json()
        else:
            _write_state(ctx, result)

    def _ci_checkpoint_shim(ctx: object) -> None:
        """Checkpoint shim: passes explicit client when model_factory is set."""
        state = _read_state(ctx)
        _c = model_factory() if model_factory is not None else None
        new_state = user_checkpoint_node(state, _client=_c)
        _write_state(ctx, new_state)

    def _ci_discovery_shim(ctx: object) -> None:
        """Discovery shim: passes explicit client when model_factory is set."""
        state = _read_state(ctx)
        _c = model_factory() if model_factory is not None else None
        new_state = discovery_turn_node(state, _client=_c)
        _write_state(ctx, new_state)

    def _ci_finalize_shim(ctx: object) -> None:
        """Finalize shim: passes explicit client when model_factory is set."""
        state = _read_state(ctx)
        _c = model_factory() if model_factory is not None else None
        new_state = finalize_master_resume_node(state, _client=_c)
        _write_state(ctx, new_state)

    def _ci_tailor_shim(ctx: object) -> None:
        """Tailor shim: passes explicit client when model_factory is set."""
        state = _read_state(ctx)
        _c = model_factory() if model_factory is not None else None
        new_state = tailor_node(state, _client=_c, _instructions=tailor_instructions)
        _write_state(ctx, new_state)

    # ── Create FunctionNode instances ─────────────────────────────────────────
    ingest = FunctionNode(func=_ci_ingest_shim, name="ingest_node")
    router = FunctionNode(func=_ci_router_shim, name="discovery_router")
    grill = FunctionNode(func=_ci_grill_shim, name="execute_grill_turn_node")
    checkpoint = FunctionNode(func=_ci_checkpoint_shim, name="user_checkpoint_node")
    discovery = FunctionNode(func=_ci_discovery_shim, name="discovery_turn_node")
    finalize = FunctionNode(func=_ci_finalize_shim, name="finalize_master_resume_node")
    tailor = FunctionNode(func=_ci_tailor_shim, name="tailor_node")

    # ── Wire edges ────────────────────────────────────────────────────────────
    # Route strings set on ctx.route by _ci_router_shim must match Edge.route values.
    #
    # TURN-BASED TOPOLOGY: there is NO back-edge from grill or checkpoint to the
    # router.  Each run_async invocation flows START → ingest → router → ONE of
    # {grill, checkpoint, finalize→tailor} and then terminates, returning control
    # to the CLI to collect the next human input.  Looping grill→router→grill in
    # a single run would spin forever (the grill node keeps asking questions with
    # no new answer to consume), so grill and checkpoint are terminal-per-turn.
    edges: list[Edge] = [
        # Entry: START → ingest
        Edge(from_node=START, to_node=ingest, route=DEFAULT_ROUTE),
        # After ingest → router
        Edge(from_node=ingest, to_node=router, route=DEFAULT_ROUTE),
        # Router branches (route strings match discovery_router return values)
        Edge(from_node=router, to_node=grill, route="execute_grill_turn_node"),
        Edge(from_node=router, to_node=checkpoint, route="user_checkpoint_node"),
        Edge(from_node=router, to_node=discovery, route="discovery_turn_node"),
        Edge(from_node=router, to_node=finalize, route="finalize_master_resume_node"),
        # discovery is terminal-per-turn (like grill/checkpoint): it asks the
        # coverage question or processes the answer, then the run ends.
        # grill is terminal-per-turn: it surfaces a question (or commits a story)
        # and the run ends; the CLI injects the next pending_user_answer.
        # checkpoint is terminal-per-turn: it emits the delta summary and pauses;
        # the CLI sets checkpoint_verified=True, then the NEXT turn re-routes to
        # checkpoint (phase==CHECKPOINT) which advances back to GRILLING.
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
    model_factory: Callable[[], ModelClient] | None = None,
    tailor_instructions: str = "",
) -> Runner:
    """Build and return an ADK 2.0 Runner wired to the discovery workflow.

    Args:
        session_service: ADK session service to use.  Defaults to
            InMemorySessionService (for testing).  Production wires in
            FirestoreSessionService (WS-C).
        app_name: Application name; must match the name used in
            session_service.create_session().
        model_factory: Optional callable returning a ModelClient.  Passed to
            ``build_discovery_workflow`` so every node in this runner instance
            uses the same per-request client instead of the process-global
            factory.  When ``None``, nodes fall back to ``_get_model_client()``.
        tailor_instructions: Optional per-application instructions forwarded
            through ``build_discovery_workflow`` to ``tailor_node``.  Appended
            to the *user* prompt so the system prompt rules remain intact.
            Defaults to ``""`` (no extra instructions).

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

    workflow = build_discovery_workflow(model_factory=model_factory, tailor_instructions=tailor_instructions)
    return Runner(
        node=workflow,
        session_service=session_service,
        app_name=app_name,
    )
