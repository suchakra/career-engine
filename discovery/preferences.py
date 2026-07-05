"""Default discovery preferences.

For the capstone demo the session rubric is seeded from the operator's real
criteria (later this becomes a per-customer intake form). Kept as a factory so
it is easy to override per user without touching the agents.
"""

from __future__ import annotations

from schema import SessionPreferences


def default_session_preferences() -> SessionPreferences:
    """Return the demo's default evaluation rubric (the operator's real criteria).

    - ``target_roles`` / ``nice_to_haves`` drive ACCEPTED vs SOFT_REJECT.
    - ``dealbreakers`` are absolute → deterministic HARD_REJECT.
    """
    return SessionPreferences(
        target_roles=[
            "Fractional Technology Leadership",
            "Consulting",
            "Principal Engineer",
        ],
        nice_to_haves=[
            "AWS",
            "SAP-C02",
            "multi-agent",
            "ADK",
            "LangGraph",
            "MCP",
            "Podman",
            "startup",
            "autonomous pipelines",
        ],
        dealbreakers=[
            "W2 middle-management",
            "bureaucratic enterprise",
            "rigid 100% on-site",
            "pure maintenance",
        ],
    )
