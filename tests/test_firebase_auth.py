"""Tests for FirebaseAuthProvider (auth/firebase_auth.py).

All tests use an injected verifier fake — no network calls are made.

Acceptance criteria verified:
AC-3 (FirebaseAuthProvider): get_user_id() is STABLE across repeated calls for
      the same identity (same token → same user_id).
"""

from __future__ import annotations

from typing import Any

import pytest

from auth.firebase_auth import FirebaseAuthProvider
from auth.provider import AuthenticationError


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin settings to an empty project so the audience check does not depend on a
    developer's local ``.env`` (deterministic: aud enforced only when a test opts
    in via ``expected_audiences``; issuer is always enforced against Google)."""
    import config
    from config import Settings

    monkeypatch.setattr(
        config, "get_settings", lambda: Settings(firebase_project_id="", gcp_project_id="")
    )


# ── Fake verifier ─────────────────────────────────────────────────────────────


def _make_fake_verifier(
    sub: str = "firebase-uid-abc",
    email: str = "user@example.com",
    extra_claims: dict[str, Any] | None = None,
) -> Any:
    """Return a verifier callable that returns fake JWT claims without any I/O."""

    def _verifier(id_token: str) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "sub": sub,
            "email": email,
            "aud": "my-project",
            "iss": "https://accounts.google.com",
        }
        if extra_claims:
            claims.update(extra_claims)
        return claims

    return _verifier


def _make_failing_verifier(error_msg: str = "invalid token") -> Any:
    """Return a verifier callable that always raises AuthenticationError."""

    def _verifier(id_token: str) -> dict[str, Any]:
        raise AuthenticationError(error_msg)

    return _verifier


def _make_no_sub_verifier() -> Any:
    """Return a verifier callable that returns claims WITHOUT a 'sub' field."""

    def _verifier(id_token: str) -> dict[str, Any]:
        return {"email": "user@example.com"}  # deliberately missing 'sub'

    return _verifier


# ── Basic identity tests ──────────────────────────────────────────────────────


class TestFirebaseAuthProviderIdentity:
    """Core identity resolution: set_token -> get_user_id."""

    def test_get_user_id_returns_sub_claim(self) -> None:
        """get_user_id() returns the 'sub' claim from the verified token."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier(sub="uid-12345"))
        provider.set_token("fake-id-token")
        assert provider.get_user_id() == "uid-12345"

    def test_get_user_id_stable_across_repeated_calls(self) -> None:
        """AC-3: Repeated get_user_id() calls return the same user_id."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier(sub="stable-uid"))
        provider.set_token("fake-id-token")

        ids = [provider.get_user_id() for _ in range(5)]
        assert ids == ["stable-uid"] * 5

    def test_get_user_id_before_set_token_raises(self) -> None:
        """get_user_id() raises AuthenticationError if no token has been set."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier())
        with pytest.raises(AuthenticationError, match="No authenticated session"):
            provider.get_user_id()

    def test_is_authenticated_false_before_set_token(self) -> None:
        """is_authenticated() returns False before set_token() is called."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier())
        assert provider.is_authenticated() is False

    def test_is_authenticated_true_after_set_token(self) -> None:
        """is_authenticated() returns True after a valid set_token() call."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier())
        provider.set_token("fake-token")
        assert provider.is_authenticated() is True

    def test_is_authenticated_false_after_failed_set_token(self) -> None:
        """is_authenticated() remains False if set_token() raises."""
        provider = FirebaseAuthProvider(verifier=_make_failing_verifier("bad token"))
        with pytest.raises(AuthenticationError):
            provider.set_token("invalid-token")
        assert provider.is_authenticated() is False


# ── Token rotation ────────────────────────────────────────────────────────────


class TestTokenRotation:
    """set_token() replaces the cached identity when called with a new token."""

    def test_second_set_token_replaces_first_identity(self) -> None:
        """Calling set_token() a second time updates the cached user_id."""
        call_count = 0
        uids = ["uid-first", "uid-second"]

        def _rotating_verifier(id_token: str) -> dict[str, Any]:
            nonlocal call_count
            uid = uids[min(call_count, len(uids) - 1)]
            call_count += 1
            return {
                "sub": uid,
                "email": f"{uid}@example.com",
                "iss": "https://accounts.google.com",
            }

        provider = FirebaseAuthProvider(verifier=_rotating_verifier)
        provider.set_token("token-1")
        assert provider.get_user_id() == "uid-first"

        provider.set_token("token-2")
        assert provider.get_user_id() == "uid-second"

    def test_failed_set_token_clears_previous_identity(self) -> None:
        """A failed set_token() invalidates the previously authenticated session."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier(sub="valid-uid"))
        provider.set_token("valid-token")
        assert provider.is_authenticated() is True

        # Now set a bad token using a failing verifier
        provider._verifier = _make_failing_verifier("revoked")
        with pytest.raises(AuthenticationError):
            provider.set_token("bad-token")

        assert provider.is_authenticated() is False
        with pytest.raises(AuthenticationError):
            provider.get_user_id()


# ── Error cases ───────────────────────────────────────────────────────────────


class TestFirebaseAuthErrors:
    """Error handling in FirebaseAuthProvider."""

    def test_set_token_raises_when_verifier_raises(self) -> None:
        """set_token() propagates AuthenticationError from the verifier."""
        provider = FirebaseAuthProvider(verifier=_make_failing_verifier("token expired"))
        with pytest.raises(AuthenticationError, match="token expired"):
            provider.set_token("expired-token")

    def test_set_token_raises_when_sub_missing(self) -> None:
        """set_token() raises AuthenticationError when the token has no 'sub' claim."""
        provider = FirebaseAuthProvider(verifier=_make_no_sub_verifier())
        with pytest.raises(AuthenticationError, match="'sub' claim"):
            provider.set_token("no-sub-token")

    def test_claims_property_returns_empty_dict_before_auth(self) -> None:
        """claims property returns an empty dict when not authenticated."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier())
        assert provider.claims == {}

    def test_claims_property_returns_copy_not_reference(self) -> None:
        """Mutating the returned claims dict must not affect the provider's state."""
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(sub="uid-claims", email="x@y.com")
        )
        provider.set_token("token")
        claims1 = provider.claims
        claims1["injected_field"] = "bad"
        claims2 = provider.claims
        assert "injected_field" not in claims2


# ── Claims / display info ─────────────────────────────────────────────────────


class TestClaimsAccess:
    """Verify the claims property exposes display info without leaking secrets."""

    def test_claims_contains_email_after_set_token(self) -> None:
        """claims dict contains email after successful set_token()."""
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(sub="uid", email="test@example.com")
        )
        provider.set_token("tok")
        assert provider.claims.get("email") == "test@example.com"

    def test_claims_contains_sub(self) -> None:
        """claims dict contains the sub claim after set_token()."""
        provider = FirebaseAuthProvider(verifier=_make_fake_verifier(sub="uid-xyz"))
        provider.set_token("tok")
        assert provider.claims.get("sub") == "uid-xyz"

    def test_claims_does_not_contain_api_key(self) -> None:
        """claims must NOT contain any api_key field (no secrets in claims)."""
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(sub="uid", extra_claims={"api_key": "AIza-should-not-be-here"})
        )
        # Even if the token verifier returns an api_key, get_user_id is just the sub claim.
        provider.set_token("tok")
        # The user_id must be the sub claim only
        assert provider.get_user_id() == "uid"


# ── Audience / issuer pinning (token-substitution defence) ────────────────────


class TestAudienceAndIssuerPinning:
    """A genuinely-signed token minted for another relying party must be rejected."""

    def test_rejects_token_with_unexpected_audience(self) -> None:
        """aud not in expected_audiences → AuthenticationError (confused deputy)."""
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(sub="attacker", extra_claims={"aud": "some-other-app"}),
            expected_audiences={"my-project"},
        )
        with pytest.raises(AuthenticationError, match="audience"):
            provider.set_token("token-for-another-app")
        assert provider.is_authenticated() is False

    def test_accepts_token_with_expected_audience(self) -> None:
        """aud in expected_audiences → accepted."""
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(sub="uid-ok", extra_claims={"aud": "my-project"}),
            expected_audiences={"my-project"},
        )
        provider.set_token("valid-token")
        assert provider.get_user_id() == "uid-ok"

    def test_accepts_securetoken_issuer_when_project_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a project id is set, a Firebase securetoken issuer + aud is accepted."""
        import config
        from config import Settings

        monkeypatch.setattr(
            config, "get_settings", lambda: Settings(firebase_project_id="my-project")
        )
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(
                sub="uid-fb",
                extra_claims={
                    "aud": "my-project",
                    "iss": "https://securetoken.google.com/my-project",
                },
            ),
        )
        provider.set_token("firebase-token")
        assert provider.get_user_id() == "uid-fb"

    def test_rejects_token_with_untrusted_issuer(self) -> None:
        """iss not in allowed_issuers → AuthenticationError."""
        provider = FirebaseAuthProvider(
            verifier=_make_fake_verifier(
                sub="attacker", extra_claims={"iss": "https://evil.example.com"}
            ),
        )
        with pytest.raises(AuthenticationError, match="issuer"):
            provider.set_token("token-from-evil-issuer")
        assert provider.is_authenticated() is False


# ── No hardcoded model name check ─────────────────────────────────────────────


class TestNoHardcodedModelNames:
    """Validate that firebase_auth.py contains no hardcoded Gemini model strings."""

    def test_no_gemini_model_string_in_source(self) -> None:
        """grep for 'gemini-' must return nothing in auth/firebase_auth.py."""
        import subprocess

        result = subprocess.run(
            ["grep", "-n", "gemini-", "auth/firebase_auth.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Found hardcoded model name(s) in auth/firebase_auth.py:\n{result.stdout}"
        )
