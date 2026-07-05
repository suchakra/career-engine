"""Unit tests for web/profile_store.py — persisted résumé-header identity.

In-memory fake WorkspaceStore, no GCP. Verifies load/save round-trip, that saving
the profile preserves the rest of the workspace, and copy-on-write.
"""

from __future__ import annotations

from schema import Application, PendingAction, UserProfile, UserWorkspace
from web.profile_store import load_profile, save_profile


class _FakeStore:
    def __init__(self) -> None:
        self._by_user: dict[str, UserWorkspace] = {}

    def load(self, user_id: str) -> UserWorkspace:
        return self._by_user.get(user_id, UserWorkspace())

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        self._by_user[user_id] = workspace


def test_new_user_has_empty_profile() -> None:
    assert load_profile(_FakeStore(), user_id="u1") == UserProfile()


def test_save_then_load_round_trips() -> None:
    store = _FakeStore()
    profile = UserProfile(
        name="Ada", email="ada@x.io", phone="123", location="Remote", links=["https://x/ada"]
    )
    save_profile(store, user_id="u1", profile=profile)
    loaded = load_profile(store, user_id="u1")
    assert loaded.name == "Ada" and loaded.links == ["https://x/ada"]


def test_save_preserves_applications_and_pending_actions() -> None:
    store = _FakeStore()
    store.save(
        "u1",
        UserWorkspace(
            applications=[Application(company="Acme")],
            pending_actions=[PendingAction(reason="follow up")],
        ),
    )
    save_profile(store, user_id="u1", profile=UserProfile(name="Ada"))
    ws = store.load("u1")
    assert ws.profile.name == "Ada"
    assert len(ws.applications) == 1 and len(ws.pending_actions) == 1


def test_save_does_not_mutate_loaded_workspace_in_place() -> None:
    store = _FakeStore()
    original = UserWorkspace()
    store.save("u1", original)  # _FakeStore returns this exact instance from load()
    save_profile(store, user_id="u1", profile=UserProfile(name="Ada"))
    assert original.profile == UserProfile()          # untouched
    assert store.load("u1").profile.name == "Ada"     # persisted copy updated


def test_users_are_isolated() -> None:
    store = _FakeStore()
    save_profile(store, user_id="u1", profile=UserProfile(name="Ada"))
    assert load_profile(store, user_id="u2") == UserProfile()


def test_load_profile_returns_a_defensive_copy() -> None:
    # Mutating the returned profile must not write through to a shared/cached store.
    store = _FakeStore()
    store.save("u1", UserWorkspace(profile=UserProfile(name="Ada")))
    loaded = load_profile(store, user_id="u1")
    loaded.name = "Mutated"
    assert store.load("u1").profile.name == "Ada"


def test_pre_v260_workspace_without_profile_key_validates() -> None:
    # Backward compat: a workspace document persisted before v2.6.0 has no 'profile'
    # key; the additive field must default (not raise), so existing users load fine.
    ws = UserWorkspace.model_validate({"applications": [], "pending_actions": []})
    assert ws.profile == UserProfile()
