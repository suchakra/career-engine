"""Unit tests for web/preferences_store.py — persisted discovery preferences (7A)."""

from __future__ import annotations

from schema import Application, PendingAction, SessionPreferences, UserProfile, UserWorkspace
from web.preferences_store import load_discovery_preferences, save_discovery_preferences


class _FakeStore:
    def __init__(self) -> None:
        self._by_user: dict[str, UserWorkspace] = {}

    def load(self, user_id: str) -> UserWorkspace:
        return self._by_user.get(user_id, UserWorkspace())

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        self._by_user[user_id] = workspace


def test_new_user_has_empty_preferences() -> None:
    assert load_discovery_preferences(_FakeStore(), user_id="u1") == SessionPreferences()


def test_save_then_load_round_trips() -> None:
    store = _FakeStore()
    prefs = SessionPreferences(
        target_roles=["Fractional CTO"], nice_to_haves=["AWS", "MCP"], dealbreakers=["on-site"]
    )
    save_discovery_preferences(store, user_id="u1", preferences=prefs)
    loaded = load_discovery_preferences(store, user_id="u1")
    assert loaded.target_roles == ["Fractional CTO"] and loaded.dealbreakers == ["on-site"]


def test_save_preserves_other_workspace_fields() -> None:
    store = _FakeStore()
    store.save(
        "u1",
        UserWorkspace(
            applications=[Application(company="Acme")],
            pending_actions=[PendingAction(reason="follow up")],
            profile=UserProfile(name="Ada"),
        ),
    )
    save_discovery_preferences(
        store, user_id="u1", preferences=SessionPreferences(target_roles=["CTO"])
    )
    ws = store.load("u1")
    assert ws.discovery_preferences.target_roles == ["CTO"]
    assert len(ws.applications) == 1 and len(ws.pending_actions) == 1
    assert ws.profile.name == "Ada"


def test_save_does_not_mutate_loaded_workspace_in_place() -> None:
    store = _FakeStore()
    original = UserWorkspace()
    store.save("u1", original)  # _FakeStore returns this exact instance from load()
    save_discovery_preferences(
        store, user_id="u1", preferences=SessionPreferences(target_roles=["CTO"])
    )
    assert original.discovery_preferences == SessionPreferences()  # untouched
    assert store.load("u1").discovery_preferences.target_roles == ["CTO"]


def test_load_returns_a_defensive_copy() -> None:
    store = _FakeStore()
    store.save("u1", UserWorkspace(discovery_preferences=SessionPreferences(target_roles=["CTO"])))
    loaded = load_discovery_preferences(store, user_id="u1")
    loaded.target_roles.append("Mutated")
    assert store.load("u1").discovery_preferences.target_roles == ["CTO"]


def test_pre_v280_workspace_without_prefs_key_validates() -> None:
    # Backward compat: a workspace persisted before v2.8.0 has no
    # 'discovery_preferences' key; the additive field must default (not raise).
    ws = UserWorkspace.model_validate({"applications": [], "pending_actions": []})
    assert ws.discovery_preferences == SessionPreferences()


def test_users_are_isolated() -> None:
    store = _FakeStore()
    save_discovery_preferences(
        store, user_id="u1", preferences=SessionPreferences(target_roles=["CTO"])
    )
    assert load_discovery_preferences(store, user_id="u2") == SessionPreferences()
