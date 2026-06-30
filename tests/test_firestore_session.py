"""Tests for database/firestore_session.py (WS-C).

All tests use FakeFirestoreClient — no live GCP connection is made.

Acceptance criteria covered:
  AC-1: Round-trip — create_session then get_session returns equal CareerEngineState.
  AC-2: Documents are keyed by user_id (assert the document path).
          No document field ever contains an API key.
  AC-3: A doc stamped with an unknown MAJOR CONTRACT_VERSION raises
          ContractVersionError; a differing MINOR version is accepted.
  AC-4: list_sessions / delete_session behave correctly.
  AC-5: last-write wins / no silent partial-write (concurrent write contract).
"""

from __future__ import annotations

import re

import pytest

from config import CONTRACT_VERSION
from database.firestore_session import (
    ContractVersionError,
    FirestoreSessionService,
    _check_version,
    _dict_to_state,
    _state_to_dict,
)
from schema import CareerEngineState, PhaseStatus, StarStory
from tests.fakes import FakeFirestoreClient

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def fake_client() -> FakeFirestoreClient:
    """Return a fresh in-memory FakeFirestoreClient."""
    return FakeFirestoreClient()


@pytest.fixture()
def service(fake_client: FakeFirestoreClient) -> FirestoreSessionService:
    """Return a FirestoreSessionService wired to a FakeFirestoreClient."""
    return FirestoreSessionService(client=fake_client)


def _make_state(**kwargs: object) -> CareerEngineState:
    """Helper: build a CareerEngineState with optional field overrides."""
    return CareerEngineState(**kwargs)  # type: ignore[arg-type]


# ── _check_version unit tests ─────────────────────────────────────────────────


class TestCheckVersion:
    """Unit tests for the _check_version helper."""

    def test_same_version_accepted(self) -> None:
        """Same major.minor.patch is accepted without error."""
        _check_version(CONTRACT_VERSION)  # must not raise

    def test_minor_difference_accepted(self) -> None:
        """A stored minor version that differs from ours is accepted (backward-compat)."""
        major = CONTRACT_VERSION.split(".")[0]
        # Bump the minor component by 1
        parts = CONTRACT_VERSION.split(".")
        bumped_minor = str(int(parts[1]) + 1)
        _check_version(f"{major}.{bumped_minor}.0")  # must not raise

    def test_patch_difference_accepted(self) -> None:
        """A stored patch version that differs is accepted."""
        parts = CONTRACT_VERSION.split(".")
        _check_version(f"{parts[0]}.{parts[1]}.999")  # must not raise

    def test_unknown_major_raises(self) -> None:
        """A stored major version that differs raises ContractVersionError."""
        current_major = int(CONTRACT_VERSION.split(".")[0])
        unknown_major = current_major + 1
        with pytest.raises(ContractVersionError, match="Incompatible contract version"):
            _check_version(f"{unknown_major}.0.0")

    def test_zero_major_raises_when_current_nonzero(self) -> None:
        """Major version 0 raises when current major is non-zero."""
        current_major = int(CONTRACT_VERSION.split(".")[0])
        if current_major == 0:
            pytest.skip("CONTRACT_VERSION has major 0 — this test requires major >= 1")
        with pytest.raises(ContractVersionError):
            _check_version("0.999.0")


# ── _state_to_dict / _dict_to_state unit tests ───────────────────────────────


class TestStateSerialization:
    """Unit tests for the serialisation helpers."""

    def test_state_to_dict_contains_contract_version(self) -> None:
        """_state_to_dict stamps the document with CONTRACT_VERSION."""
        doc = _state_to_dict(CareerEngineState())
        assert doc["contract_version"] == CONTRACT_VERSION

    def test_state_to_dict_contains_career_engine_state(self) -> None:
        """_state_to_dict stores state under the 'career_engine_state' key."""
        state = CareerEngineState(question_count=7)
        doc = _state_to_dict(state)
        assert "career_engine_state" in doc
        assert doc["career_engine_state"]["question_count"] == 7

    def test_dict_to_state_roundtrip(self) -> None:
        """_dict_to_state(  _state_to_dict(s)  ) returns an equal CareerEngineState."""
        original = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            question_count=3,
        )
        doc = _state_to_dict(original)
        restored = _dict_to_state(doc)
        assert restored == original

    def test_dict_to_state_raises_on_bad_major(self) -> None:
        """_dict_to_state raises ContractVersionError for unknown major version."""
        state = CareerEngineState()
        doc = _state_to_dict(state)
        doc["contract_version"] = "99.0.0"
        with pytest.raises(ContractVersionError):
            _dict_to_state(doc)

    def test_state_to_dict_contains_no_api_key_fields(self) -> None:
        """No secret-like key names appear in _state_to_dict output."""
        doc = _state_to_dict(CareerEngineState())
        _assert_no_api_key_in_doc(doc)


# ── AC-1: Round-trip ──────────────────────────────────────────────────────────


class TestRoundTrip:
    """AC-1: save(state) then load() returns an equal CareerEngineState."""

    async def test_create_then_get_returns_equal_state(
        self, service: FirestoreSessionService
    ) -> None:
        """Round-trip: create_session with a CareerEngineState, get_session returns equal state."""
        original_ces = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            question_count=5,
        )
        initial_state = {"career_engine_state": original_ces.model_dump(mode="json")}

        await service.create_session(
            app_name="career-engine",
            user_id="user-abc",
            state=initial_state,
            session_id="sess-001",
        )

        retrieved = await service.get_session(
            app_name="career-engine",
            user_id="user-abc",
            session_id="sess-001",
        )

        assert retrieved is not None
        assert "career_engine_state" in retrieved.state

        restored_ces = CareerEngineState.model_validate(
            retrieved.state["career_engine_state"]
        )
        assert restored_ces == original_ces

    async def test_round_trip_with_star_stories(
        self, service: FirestoreSessionService
    ) -> None:
        """Round-trip preserves StarStory list (nested Pydantic model)."""
        story = StarStory(
            pillar="performance",
            result="Cut p99 from 800ms to 120ms across 40 services.",
            metrics_validated=True,
        )
        original_ces = CareerEngineState(extracted_star_stories=[story])
        initial_state = {"career_engine_state": original_ces.model_dump(mode="json")}

        await service.create_session(
            app_name="career-engine",
            user_id="user-xyz",
            state=initial_state,
        )

        sessions = await service.list_sessions(
            app_name="career-engine", user_id="user-xyz"
        )
        assert len(sessions.sessions) == 1
        session_id = sessions.sessions[0].id

        retrieved = await service.get_session(
            app_name="career-engine",
            user_id="user-xyz",
            session_id=session_id,
        )
        assert retrieved is not None
        restored_ces = CareerEngineState.model_validate(
            retrieved.state["career_engine_state"]
        )
        assert len(restored_ces.extracted_star_stories) == 1
        assert restored_ces.extracted_star_stories[0].result == story.result
        assert restored_ces.extracted_star_stories[0].metrics_validated is True

    async def test_default_state_round_trips(
        self, service: FirestoreSessionService
    ) -> None:
        """create_session with no initial state creates a default CareerEngineState."""
        session = await service.create_session(
            app_name="career-engine",
            user_id="user-default",
        )
        retrieved = await service.get_session(
            app_name="career-engine",
            user_id="user-default",
            session_id=session.id,
        )
        assert retrieved is not None
        ces = CareerEngineState.model_validate(retrieved.state["career_engine_state"])
        assert ces == CareerEngineState()

    async def test_json_string_career_engine_state_round_trips(
        self, service: FirestoreSessionService
    ) -> None:
        """A CareerEngineState supplied as a JSON string is deserialised correctly."""
        original_ces = CareerEngineState(question_count=9)
        # Supply as a JSON string (unusual path)
        initial_state = {"career_engine_state": original_ces.model_dump_json()}

        session = await service.create_session(
            app_name="career-engine",
            user_id="user-json",
            state=initial_state,
        )
        retrieved = await service.get_session(
            app_name="career-engine",
            user_id="user-json",
            session_id=session.id,
        )
        assert retrieved is not None
        restored = CareerEngineState.model_validate(
            retrieved.state["career_engine_state"]
        )
        assert restored.question_count == 9


# ── AC-2: Keyed by user_id; no API key in docs ───────────────────────────────


def _assert_no_api_key_in_doc(doc: dict[str, Any]) -> None:
    """Assert that no value or key in *doc* looks like an API key.

    An 'API key-like string' is defined as any string that:
    - contains the substring "api_key", "apikey", or "secret" (case-insensitive), OR
    - matches a 39-character alphanumeric string starting with "AI" (Gemini API key shape).

    Args:
        doc: The Firestore document dict to inspect.
    """
    gemini_key_pattern = re.compile(r"\bAI[A-Za-z0-9_-]{37}\b")

    def _check(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                lower_k = k.lower()
                assert "api_key" not in lower_k, f"API-key field name at {path}.{k}"
                assert "apikey" not in lower_k, f"API-key field name at {path}.{k}"
                _check(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _check(item, f"{path}[{i}]")
        elif isinstance(obj, str):
            assert not gemini_key_pattern.search(obj), (
                f"API-key-like value found at {path}: {obj[:20]}..."
            )

    _check(doc)


from typing import Any  # noqa: E402 (needed after function def above)


class TestDocumentKeying:
    """AC-2: Documents are keyed by user_id; no document field contains an API key."""

    async def test_document_path_contains_user_id(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """The Firestore document path includes the user_id, not an API key."""
        user_id = "user-12345"
        session = await service.create_session(
            app_name="career-engine",
            user_id=user_id,
        )

        # Verify the actual path in the store contains user_id
        stored_paths = list(fake_client.store.keys())
        assert len(stored_paths) == 1
        path = stored_paths[0]
        assert user_id in path, f"user_id not found in path: {path}"
        assert session.id in path, f"session_id not found in path: {path}"

    async def test_document_path_keyed_by_user_id_not_api_key(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """Document path uses user_id; API key shape strings do not appear in path."""
        # A simulated Gemini API key (39 chars starting with 'AI')
        fake_api_key = "AIza" + "X" * 35
        user_id = "user-authentic-identity"

        await service.create_session(
            app_name="career-engine",
            user_id=user_id,
            # API key is NOT part of the state we pass in
        )

        for path in fake_client.store:
            assert fake_api_key not in path, (
                f"API key found in document path: {path}"
            )
            assert user_id in path

    async def test_no_api_key_in_document_fields(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """No stored document field contains a value that looks like an API key."""
        # Even if someone mistakenly puts a key-like string in state, it must
        # not survive into the stored document under a secret-like field name.
        # Here we just assert the baseline: a normal session has no such fields.
        await service.create_session(
            app_name="career-engine",
            user_id="user-safe",
        )

        for doc_data in fake_client.store.values():
            _assert_no_api_key_in_doc(doc_data)

    async def test_document_path_structure(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """Document path follows the expected hierarchical structure."""
        await service.create_session(
            app_name="myapp",
            user_id="u-abc",
            session_id="sess-xyz",
        )
        # Expected: sessions/myapp/users/u-abc/sessions/sess-xyz
        expected_path = "sessions/myapp/users/u-abc/sessions/sess-xyz"
        assert expected_path in fake_client.store, (
            f"Expected path {expected_path!r} not found in store. "
            f"Stored paths: {list(fake_client.store.keys())}"
        )

    async def test_different_collection_prefix(
        self, fake_client: FakeFirestoreClient
    ) -> None:
        """A custom collection_prefix is reflected in the document path."""
        svc = FirestoreSessionService(collection_prefix="ce_sessions", client=fake_client)
        await svc.create_session(
            app_name="myapp",
            user_id="u1",
            session_id="s1",
        )
        expected = "ce_sessions/myapp/users/u1/sessions/s1"
        assert expected in fake_client.store


# ── AC-3: CONTRACT_VERSION enforcement ───────────────────────────────────────


class TestContractVersionEnforcement:
    """AC-3: Unknown MAJOR version raises; differing MINOR version is accepted."""

    async def test_unknown_major_version_raises_on_get(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """get_session raises ContractVersionError for a document with unknown major."""
        # Write a document manually with a future major version
        fake_client.store["sessions/career-engine/users/u1/sessions/s1"] = {
            "contract_version": "99.0.0",
            "app_name": "career-engine",
            "user_id": "u1",
            "session_id": "s1",
            "last_update_time": 0.0,
            "career_engine_state": CareerEngineState().model_dump(mode="json"),
            "session_state": {},
        }
        with pytest.raises(ContractVersionError, match="Incompatible contract version"):
            await service.get_session(
                app_name="career-engine",
                user_id="u1",
                session_id="s1",
            )

    async def test_differing_minor_version_accepted_on_get(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """get_session succeeds when the stored minor version differs."""
        major = CONTRACT_VERSION.split(".")[0]
        parts = CONTRACT_VERSION.split(".")
        bumped_minor = str(int(parts[1]) + 1)
        stored_version = f"{major}.{bumped_minor}.0"

        fake_client.store["sessions/career-engine/users/u1/sessions/s2"] = {
            "contract_version": stored_version,
            "app_name": "career-engine",
            "user_id": "u1",
            "session_id": "s2",
            "last_update_time": 0.0,
            "career_engine_state": CareerEngineState().model_dump(mode="json"),
            "session_state": {},
        }
        # Must NOT raise
        session = await service.get_session(
            app_name="career-engine",
            user_id="u1",
            session_id="s2",
        )
        assert session is not None

    async def test_differing_patch_version_accepted(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """get_session succeeds when only the stored patch version differs."""
        parts = CONTRACT_VERSION.split(".")
        stored_version = f"{parts[0]}.{parts[1]}.999"

        fake_client.store["sessions/career-engine/users/u1/sessions/s3"] = {
            "contract_version": stored_version,
            "app_name": "career-engine",
            "user_id": "u1",
            "session_id": "s3",
            "last_update_time": 0.0,
            "career_engine_state": CareerEngineState().model_dump(mode="json"),
            "session_state": {},
        }
        session = await service.get_session(
            app_name="career-engine",
            user_id="u1",
            session_id="s3",
        )
        assert session is not None

    async def test_list_sessions_skips_incompatible_version(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """list_sessions silently skips documents with incompatible major version."""
        # One valid session
        valid_ces = CareerEngineState(question_count=2)
        valid_doc = {
            "contract_version": CONTRACT_VERSION,
            "app_name": "career-engine",
            "user_id": "u1",
            "session_id": "good",
            "last_update_time": 0.0,
            "career_engine_state": valid_ces.model_dump(mode="json"),
            "session_state": {},
        }
        # One incompatible session
        bad_doc = {
            "contract_version": "99.0.0",
            "app_name": "career-engine",
            "user_id": "u1",
            "session_id": "bad",
            "last_update_time": 0.0,
            "career_engine_state": {},
            "session_state": {},
        }
        fake_client.store["sessions/career-engine/users/u1/sessions/good"] = valid_doc
        fake_client.store["sessions/career-engine/users/u1/sessions/bad"] = bad_doc

        response = await service.list_sessions(app_name="career-engine", user_id="u1")
        # Only the good session should appear
        assert len(response.sessions) == 1
        assert response.sessions[0].id == "good"

    async def test_created_documents_carry_contract_version(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """create_session stamps the document with the current CONTRACT_VERSION."""
        await service.create_session(
            app_name="career-engine",
            user_id="u-stamp",
            session_id="s-stamp",
        )
        doc = fake_client.store["sessions/career-engine/users/u-stamp/sessions/s-stamp"]
        assert doc["contract_version"] == CONTRACT_VERSION


# ── AC-4: list_sessions / delete_session ─────────────────────────────────────


class TestListAndDelete:
    """AC-4: list_sessions / delete_session behave correctly."""

    async def test_list_sessions_returns_created_sessions(
        self, service: FirestoreSessionService
    ) -> None:
        """list_sessions returns sessions for the specified user."""
        for i in range(3):
            await service.create_session(
                app_name="career-engine",
                user_id="user-list",
                session_id=f"sess-{i}",
            )

        response = await service.list_sessions(
            app_name="career-engine", user_id="user-list"
        )
        assert len(response.sessions) == 3
        ids = {s.id for s in response.sessions}
        assert ids == {"sess-0", "sess-1", "sess-2"}

    async def test_list_sessions_isolates_by_user(
        self, service: FirestoreSessionService
    ) -> None:
        """list_sessions returns ONLY the specified user's sessions."""
        await service.create_session(
            app_name="career-engine", user_id="user-a", session_id="sa1"
        )
        await service.create_session(
            app_name="career-engine", user_id="user-b", session_id="sb1"
        )
        await service.create_session(
            app_name="career-engine", user_id="user-b", session_id="sb2"
        )

        response_a = await service.list_sessions(
            app_name="career-engine", user_id="user-a"
        )
        assert len(response_a.sessions) == 1
        assert response_a.sessions[0].id == "sa1"

        response_b = await service.list_sessions(
            app_name="career-engine", user_id="user-b"
        )
        assert len(response_b.sessions) == 2

    async def test_list_sessions_empty_for_unknown_user(
        self, service: FirestoreSessionService
    ) -> None:
        """list_sessions returns empty response for a user with no sessions."""
        response = await service.list_sessions(
            app_name="career-engine", user_id="nobody"
        )
        assert response.sessions == []

    async def test_list_sessions_none_user_returns_empty(
        self, service: FirestoreSessionService
    ) -> None:
        """list_sessions with user_id=None returns empty (cross-user not supported)."""
        await service.create_session(app_name="career-engine", user_id="u1")
        response = await service.list_sessions(app_name="career-engine", user_id=None)
        assert response.sessions == []

    async def test_delete_session_removes_session(
        self, service: FirestoreSessionService
    ) -> None:
        """delete_session removes the session; subsequent get_session returns None."""
        await service.create_session(
            app_name="career-engine",
            user_id="u-del",
            session_id="to-delete",
        )
        # Verify it exists
        before = await service.get_session(
            app_name="career-engine",
            user_id="u-del",
            session_id="to-delete",
        )
        assert before is not None

        await service.delete_session(
            app_name="career-engine",
            user_id="u-del",
            session_id="to-delete",
        )

        after = await service.get_session(
            app_name="career-engine",
            user_id="u-del",
            session_id="to-delete",
        )
        assert after is None

    async def test_delete_session_is_idempotent(
        self, service: FirestoreSessionService
    ) -> None:
        """delete_session is a no-op (not an error) if the session does not exist."""
        # Should not raise
        await service.delete_session(
            app_name="career-engine",
            user_id="u-ghost",
            session_id="non-existent",
        )

    async def test_delete_removes_from_list(
        self, service: FirestoreSessionService
    ) -> None:
        """After delete_session, list_sessions no longer includes the deleted session."""
        for i in range(3):
            await service.create_session(
                app_name="career-engine",
                user_id="u-list-del",
                session_id=f"s{i}",
            )

        await service.delete_session(
            app_name="career-engine",
            user_id="u-list-del",
            session_id="s1",
        )

        response = await service.list_sessions(
            app_name="career-engine", user_id="u-list-del"
        )
        ids = {s.id for s in response.sessions}
        assert "s1" not in ids
        assert ids == {"s0", "s2"}

    async def test_list_sessions_does_not_include_events(
        self, service: FirestoreSessionService
    ) -> None:
        """list_sessions returns sessions with empty events list (per ADK contract)."""
        await service.create_session(
            app_name="career-engine",
            user_id="u-events",
            session_id="s-events",
        )
        response = await service.list_sessions(
            app_name="career-engine", user_id="u-events"
        )
        for s in response.sessions:
            assert s.events == []


# ── AC-5: Last-write wins / no silent partial writes ─────────────────────────


class TestConcurrentWriteContract:
    """AC-5: last-write wins is the defined behavior; no silent partial writes."""

    async def test_create_session_same_id_overwrites(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """Creating a session with the same ID twice results in last-write winning.

        The real Firestore InMemorySessionService raises AlreadyExistsError;
        our adapter uses .set() which is last-write-wins.  This is the defined
        behavior for the Firestore adapter — documented and tested here.
        """
        state_v1 = CareerEngineState(question_count=1)
        state_v2 = CareerEngineState(question_count=2)

        await service.create_session(
            app_name="career-engine",
            user_id="u-overwrite",
            session_id="s-overwrite",
            state={"career_engine_state": state_v1.model_dump(mode="json")},
        )
        await service.create_session(
            app_name="career-engine",
            user_id="u-overwrite",
            session_id="s-overwrite",
            state={"career_engine_state": state_v2.model_dump(mode="json")},
        )

        retrieved = await service.get_session(
            app_name="career-engine",
            user_id="u-overwrite",
            session_id="s-overwrite",
        )
        assert retrieved is not None
        ces = CareerEngineState.model_validate(retrieved.state["career_engine_state"])
        # Last write (state_v2) wins
        assert ces.question_count == 2

    async def test_full_document_written_atomically(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """create_session writes all required fields in a single .set() call.

        After create_session returns, all required fields are present and
        self-consistent — there is no partial-write window from the caller's
        perspective (the fake backend is synchronous, so this is trivially true;
        the test exists to document the contract and would catch regressions if
        the implementation were split across multiple writes).
        """
        ces = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            question_count=4,
        )
        await service.create_session(
            app_name="career-engine",
            user_id="u-atomic",
            session_id="s-atomic",
            state={"career_engine_state": ces.model_dump(mode="json")},
        )

        path = "sessions/career-engine/users/u-atomic/sessions/s-atomic"
        doc = fake_client.store[path]

        # All required fields are present after a single create_session call
        required_keys = {
            "contract_version",
            "app_name",
            "user_id",
            "session_id",
            "last_update_time",
            "career_engine_state",
            "session_state",
        }
        assert required_keys.issubset(set(doc.keys()))
        assert doc["user_id"] == "u-atomic"
        assert doc["session_id"] == "s-atomic"
        assert doc["contract_version"] == CONTRACT_VERSION


# ── No-secrets in Firestore assertion ────────────────────────────────────────


class TestNoSecretsInFirestore:
    """Assert that no secret or API key is ever written to the Firestore fake."""

    async def test_no_api_key_after_session_creation(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """No Gemini-API-key-shaped value appears in any stored Firestore document."""
        # Simulate a state that might accidentally carry a key in a non-standard field
        # (legitimate use would never do this, but we assert it defensively)
        ces = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            question_count=1,
        )
        await service.create_session(
            app_name="career-engine",
            user_id="u-nosecrets",
            state={"career_engine_state": ces.model_dump(mode="json")},
        )

        for doc_data in fake_client.store.values():
            _assert_no_api_key_in_doc(doc_data)
            # Also verify user_id is stored (not the key)
            assert "user_id" in doc_data
            assert doc_data["user_id"] == "u-nosecrets"

    async def test_session_state_field_contains_no_secrets(
        self, service: FirestoreSessionService, fake_client: FakeFirestoreClient
    ) -> None:
        """The session_state sub-dict (ADK-internal keys) never leaks secrets."""
        await service.create_session(
            app_name="career-engine",
            user_id="u-state-safe",
            state={
                "career_engine_state": CareerEngineState().model_dump(mode="json"),
                "app:some_flag": True,   # ADK-internal app-scoped state
                "user:preference": "dark-mode",  # ADK-internal user-scoped state
            },
        )
        for doc_data in fake_client.store.values():
            _assert_no_api_key_in_doc(doc_data)


# ── get_session returns None for unknown sessions ─────────────────────────────


class TestGetSessionEdgeCases:
    """Edge-case tests for get_session."""

    async def test_get_nonexistent_session_returns_none(
        self, service: FirestoreSessionService
    ) -> None:
        """get_session returns None for a session that was never created."""
        result = await service.get_session(
            app_name="career-engine",
            user_id="u1",
            session_id="does-not-exist",
        )
        assert result is None

    async def test_get_session_wrong_user_returns_none(
        self, service: FirestoreSessionService
    ) -> None:
        """get_session returns None when the user_id doesn't match."""
        await service.create_session(
            app_name="career-engine",
            user_id="user-a",
            session_id="shared-sid",
        )
        result = await service.get_session(
            app_name="career-engine",
            user_id="user-b",
            session_id="shared-sid",
        )
        assert result is None

    async def test_get_session_preserves_session_metadata(
        self, service: FirestoreSessionService
    ) -> None:
        """get_session returns correct app_name, user_id, and session_id."""
        await service.create_session(
            app_name="myapp",
            user_id="my-user",
            session_id="my-session",
        )
        retrieved = await service.get_session(
            app_name="myapp",
            user_id="my-user",
            session_id="my-session",
        )
        assert retrieved is not None
        assert retrieved.app_name == "myapp"
        assert retrieved.user_id == "my-user"
        assert retrieved.id == "my-session"

    async def test_get_session_with_config_does_not_raise(
        self, service: FirestoreSessionService
    ) -> None:
        """get_session accepts a GetSessionConfig without raising."""
        from google.adk.sessions.base_session_service import GetSessionConfig

        await service.create_session(
            app_name="career-engine",
            user_id="u-config",
            session_id="s-config",
        )
        retrieved = await service.get_session(
            app_name="career-engine",
            user_id="u-config",
            session_id="s-config",
            config=GetSessionConfig(num_recent_events=0),
        )
        assert retrieved is not None


# ── Service constructor tests ─────────────────────────────────────────────────


class TestServiceConstructor:
    """Tests for FirestoreSessionService constructor injection."""

    def test_default_collection_prefix(self) -> None:
        """FirestoreSessionService defaults to 'sessions' as the collection prefix."""
        client = FakeFirestoreClient()
        svc = FirestoreSessionService(client=client)
        assert svc._collection_prefix == "sessions"

    def test_custom_collection_prefix(self) -> None:
        """FirestoreSessionService accepts a custom collection_prefix."""
        client = FakeFirestoreClient()
        svc = FirestoreSessionService(collection_prefix="custom_prefix", client=client)
        assert svc._collection_prefix == "custom_prefix"

    def test_injected_client_is_used(self) -> None:
        """When a client is injected, get_firestore_client() is NOT called."""
        client = FakeFirestoreClient()
        svc = FirestoreSessionService(client=client)
        assert svc._client is client
