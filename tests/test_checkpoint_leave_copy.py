"""Test that the checkpoint leave-copy info message is shown (WS 9J)."""

from __future__ import annotations

from typing import Any

import web.grill_ui as grill_ui


class _NullCtx:
    """Context manager that also accepts arbitrary attribute calls (e.g. c1.caption)."""

    def __enter__(self) -> _NullCtx:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        return lambda *a, **kw: None


class _FakeSt:
    """Minimal fake for streamlit to exercise the grill render path."""

    def __init__(self, session_state: dict[str, Any]) -> None:
        self.session_state = session_state
        self._null = _NullCtx()
        self.infos: list[str] = []

    def columns(self, spec: int | list[Any] = 1, **kwargs: Any) -> list[_NullCtx]:
        n = spec if isinstance(spec, int) else len(spec)
        return [_NullCtx() for _ in range(n)]

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def title(self, *args: Any, **kwargs: Any) -> None:
        pass

    def info(self, msg: str, **kwargs: Any) -> None:
        self.infos.append(msg)

    def caption(self, *args: Any, **kwargs: Any) -> None:
        pass

    def write(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass

    def success(self, *args: Any, **kwargs: Any) -> None:
        pass

    def chat_message(self, *args: Any, **kwargs: Any) -> _NullCtx:
        return self._null

    def rerun(self) -> None:
        pass


def _make_ss(checkpoint: str) -> dict[str, Any]:
    """Session state that puts render_grill directly at the checkpoint block."""
    return {
        "grill_started": True,
        "grill_checkpoint": checkpoint,
        "grill_complete": False,
        "grill_transcript": [],
        # grill_resumed absent → ss.pop("grill_resumed", False) returns False
        # grill_entry_label absent → skip the "currently grilling" info
        # grill_key_persisted absent → takes the else branch (caption only)
        "grill_key_persisted": False,
    }


def test_checkpoint_leave_copy_shown(monkeypatch: Any) -> None:
    """Info message about checkpoint / Portfolio is rendered when grill_checkpoint is set."""
    ss = _make_ss("Great work so far — here is your checkpoint summary.")
    fake_st = _FakeSt(ss)

    monkeypatch.setattr(grill_ui, "st", fake_st)
    # Bypass the BYOK key-lookup (returns truthy → key resolved)
    monkeypatch.setattr(grill_ui, "_resolve_key", lambda user_id: "fake-key")
    # Bypass storage-backend check (non-InMemorySessionService → no warning)
    monkeypatch.setattr(
        grill_ui,
        "_grill_session_service",
        lambda: object(),
    )

    grill_ui.render_grill(user_id="test-user")

    assert any("checkpoint" in msg for msg in fake_st.infos), (
        f"Expected checkpoint info in an st.info() call, got: {fake_st.infos}"
    )
