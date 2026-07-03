"""Interactive "Grill Me" chat for the web workspace (Phase 2A web grill).

Drives the SAME turn-based discovery graph the CLI uses (``DiscoverySession``),
rendered as a Streamlit chat. Bring-your-own-key (BYOK): the user pastes their own
Gemini API key so grilling runs on THEIR quota (no shared platform key, no
free-tier bottleneck) — consistent with the privacy-first design (ARCHITECTURE §5).

State lives in ``st.session_state`` (per browser session): the live
``DiscoverySession`` (in-memory ADK session service), the transcript, the current
question / checkpoint, and the BYOK key (session-only, never persisted).

Note: the discovery nodes resolve their model client from a process-global factory
(``workflows.nodes``), so this UI targets ONE user per server instance — fine for
the single-user demo (Cloud Run is pinned to one instance).
"""

from __future__ import annotations

import asyncio
import pathlib
import tempfile
from datetime import date
from typing import Any, cast

import streamlit as st
from google.adk.sessions import BaseSessionService, InMemorySessionService

from auth.key_vault import SecretManagerKeyVault
from cli.app import (
    DiscoverySession,
    TurnResult,
    _install_model_client,
    guess_resume_mime,
)
from config import AccessMode
from integration.model_client import GeminiModelClient, ModelAPIError
from schema import Entry

_MAX_AUTO_TURNS = 6  # bound the non-interactive drive to finalize
_METRIC_NUDGE = (
    "Could you put a specific number on that — roughly how many, what percent, or how "
    "much time or cost was saved?"
)


def _resolve_key(user_id: str) -> str | None:
    """Return the user's BYOK key: session cache → Secret Manager (set once)."""
    ss = st.session_state
    if ss.get("grill_force_key_prompt"):
        return None
    if ss.get("grill_key"):
        return str(ss["grill_key"])
    try:
        vault = SecretManagerKeyVault()
        if vault.key_exists(user_id):
            key = vault.fetch_key(user_id)
            ss["grill_key"] = key
            ss["grill_key_persisted"] = True
            return key
    except Exception:
        pass  # no vault / no perms → fall through to prompt
    return None


def _store_key(user_id: str, key: str) -> None:
    """Persist the BYOK key in Secret Manager (keyed by identity); cache in session.

    Falls back to session-only if the app can't write to Secret Manager, so the
    grill still works either way.
    """
    ss = st.session_state
    ss["grill_key"] = key
    ss["grill_key_persisted"] = False
    ss.pop("grill_force_key_prompt", None)
    try:
        SecretManagerKeyVault().store_key(user_id, key)
        ss["grill_key_persisted"] = True
    except Exception:
        pass  # session-only fallback


def _show_model_error(exc: ModelAPIError) -> None:
    """Render a friendly, non-crashing message for a model/quota failure."""
    if exc.is_rate_limited:
        retry = (
            f" Try again in ~{exc.retry_after_seconds:.0f}s."
            if exc.retry_after_seconds is not None
            else ""
        )
        st.error(
            f"⏳ Gemini rate limit / quota reached on your key.{retry} "
            "The free tier is 5 requests/min and 20/day — a paid or higher-quota key "
            "removes this."
        )
    else:
        st.error(f"⚠️ Model error: {exc}")


def _apply_turn(turn: TurnResult) -> None:
    """Fold a TurnResult into session_state (question / checkpoint / complete)."""
    ss = st.session_state
    if turn.upgrade_required:
        st.warning(turn.upgrade_message or "This step needs a more capable model.")
        ss["grill_question"] = turn.next_question
        return
    if turn.checkpoint_summary:
        ss["grill_checkpoint"] = turn.checkpoint_summary
        ss["grill_question"] = ""
        return
    if turn.is_complete:
        ss["grill_complete"] = True
        ss["grill_question"] = ""
        return
    ss["grill_checkpoint"] = ""
    # Never show a blank question — if the model returned an empty follow-up, nudge
    # for a concrete metric rather than leaving the user staring at nothing.
    ss["grill_question"] = turn.next_question or _METRIC_NUDGE


def _start_session(
    user_id: str, history: str, work_timeline: list[Entry] | None = None
) -> None:
    """Create a DiscoverySession on the BYOK key and run the opening turn.

    ``work_timeline`` seeds pre-parsed entries (résumé vision ingest) instead of
    parsing ``history`` text.
    """
    ss = st.session_state
    client = GeminiModelClient(api_key=ss["grill_key"])
    svc = cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]
    session = DiscoverySession(
        user_id=user_id,
        # Deliberate: FREE routes grilling to Flash (cheap) even though we run on the
        # user's own key — BYOK here means "your quota", not "unlock Pro". BYOK→Pro
        # would cost materially more; Flash+CoT is the design's baseline.
        access_mode=AccessMode.FREE,
        model_client=client,
        session_service=svc,
    )
    try:
        with st.spinner("Reading your history and preparing the first question…"):
            question = asyncio.run(
                session.start(
                    history,
                    reference_date=date.today().isoformat(),
                    work_timeline=work_timeline,
                )
            )
    except ModelAPIError as exc:
        _show_model_error(exc)
        return

    ss["grill_client"] = client
    ss["grill_session"] = session
    ss["grill_transcript"] = []
    ss["grill_question"] = question
    ss["grill_checkpoint"] = ""
    ss["grill_complete"] = False
    ss["grill_started"] = True
    st.rerun()


def _submit_answer(answer: str) -> None:
    """Record an answer, run a turn, and drive any non-interactive turns."""
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    ss["grill_transcript"].append(("agent", ss.get("grill_question", "")))
    ss["grill_transcript"].append(("user", answer))
    try:
        with st.spinner("Thinking…"):
            before = asyncio.run(session.current_state())
            turn = asyncio.run(session.answer(answer))
            after = asyncio.run(session.current_state())
            # Only auto-advance when the answer was ACCEPTED (a story was committed
            # → the frontier moved on to the next entry / finalize). On a vague answer
            # nothing is committed and the turn carries a probe; advancing here would
            # re-run the grill with no pending answer and re-ask the entry's OPENING
            # question. Grill is terminal-per-turn, so drive finalize only post-accept.
            accepted = len(after.extracted_star_stories) > len(before.extracted_star_stories)
            if accepted:
                for _ in range(_MAX_AUTO_TURNS):
                    if (
                        turn.upgrade_required
                        or turn.is_complete
                        or turn.checkpoint_summary
                        or turn.next_question
                    ):
                        break
                    turn = asyncio.run(session.advance())
    except ModelAPIError as exc:
        _show_model_error(exc)
        return
    _apply_turn(turn)
    st.rerun()


def _confirm_checkpoint() -> None:
    """Confirm the checkpoint and continue grilling."""
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    ss["grill_transcript"].append(("agent", f"[checkpoint] {ss.get('grill_checkpoint', '')}"))
    ss["grill_transcript"].append(("user", "Looks right — keep going."))
    try:
        with st.spinner("Continuing…"):
            question = asyncio.run(session.confirm_checkpoint())
    except ModelAPIError as exc:
        _show_model_error(exc)
        return
    ss["grill_checkpoint"] = ""
    ss["grill_question"] = question
    st.rerun()


def _offer_pdf() -> None:
    """Render the completed résumé to a downloadable PDF."""
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    if st.button("Generate résumé PDF", type="primary"):
        try:
            with st.spinner("Rendering your résumé…"):
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    out = asyncio.run(session.render_resume_pdf(pathlib.Path(tf.name)))
                data = out.read_bytes()
                out.unlink(missing_ok=True)  # don't orphan the temp file
            st.download_button(
                "⬇️ Download résumé.pdf",
                data=data,
                file_name="careerengine_resume.pdf",
                mime="application/pdf",
            )
        except Exception as exc:  # rendering is best-effort in the UI
            st.error(f"Could not render the PDF: {exc}")


def _start_from_resume(user_id: str, uploaded: Any) -> None:
    """Vision-parse an uploaded résumé into a timeline, then start the session."""
    from tools.resume_parser import ParseError, parse_resume

    ss = st.session_state
    data: bytes = uploaded.getvalue()
    # Prefer the browser-supplied MIME; fall back to a filename guess (never a
    # blind pdf default, which could mis-label an image).
    mime = uploaded.type or guess_resume_mime(pathlib.Path(uploaded.name))
    client = GeminiModelClient(api_key=ss["grill_key"])
    try:
        with st.spinner("Reading your résumé…"):
            entries = parse_resume(data, mime, client=client)
    except ModelAPIError as exc:
        _show_model_error(exc)
        return
    except ParseError as exc:
        st.error(f"Couldn't read that résumé: {exc}")
        return
    _start_session(user_id, "", work_timeline=entries)


def _revoke_key(user_id: str) -> None:
    """Delete the user's stored key (revoke) and force a re-prompt."""
    ss = st.session_state
    try:
        SecretManagerKeyVault().delete_key(user_id)
    except Exception:
        pass
    ss.pop("grill_key", None)
    ss.pop("grill_key_persisted", None)
    ss["grill_force_key_prompt"] = True


def _reset() -> None:
    """Clear all grill state (start over)."""
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("grill_"):
            del st.session_state[k]


def render_grill(*, user_id: str) -> None:
    """Render the interactive grill view."""
    top = st.columns([1, 1, 6])
    with top[0]:
        if st.button("← Dashboard"):
            st.session_state["view"] = "dashboard"
            st.rerun()
    with top[1]:
        if st.button("↺ Restart"):
            _reset()
            st.rerun()

    st.title("Grill Me")

    ss = st.session_state

    # ── Step 1: BYOK key (set once — persisted per identity in Secret Manager) ─
    if not _resolve_key(user_id):
        st.info(
            "Grilling runs on **your own Gemini API key** — get one free at "
            "https://aistudio.google.com/apikey."
        )
        st.caption(
            "Saving stores it in Google Secret Manager (encrypted at rest, keyed to your "
            "account, never in the database or logs). You can remove it anytime."
        )
        key = st.text_input("Gemini API key", type="password")
        if st.button("Save & use this key", type="primary") and key.strip():
            _store_key(user_id, key.strip())
            st.rerun()
        return

    if ss.get("grill_key_persisted"):
        c1, c2 = st.columns([3, 1])
        c1.caption("🔑 Using your saved Gemini key.")
        if c2.button("Remove key"):
            _revoke_key(user_id)
            st.rerun()
    else:
        st.caption("🔑 Using your Gemini key (this session only — couldn't persist).")

    # ── Step 2: seed from a résumé upload OR pasted history ───────────────────
    if not ss.get("grill_started"):
        st.write("**Start from your résumé** (vision-parsed), or paste your history below.")
        resume = st.file_uploader(
            "Résumé (PDF / PNG / JPG / WEBP)",
            type=["pdf", "png", "jpg", "jpeg", "webp"],
        )
        history = st.text_area(
            "…or paste your career history (rough is fine — the agent pushes for specifics)",
            height=180,
            key="grill_history_input",
        )
        cols = st.columns([1, 1, 4])
        with cols[0]:
            start = st.button("Start grilling", type="primary")
        with cols[1]:
            if st.button("Change key"):
                ss.pop("grill_key", None)
                ss["grill_force_key_prompt"] = True
                st.rerun()
        if start:
            if resume is not None:
                _start_from_resume(user_id, resume)
            elif history.strip():
                _start_session(user_id, history)
            else:
                st.warning("Upload a résumé or paste some history to begin.")
        return

    # ── Step 3: the conversation ──────────────────────────────────────────────
    _install_model_client(ss["grill_client"])  # ensure nodes use this user's key

    for role, text in ss.get("grill_transcript", []):
        with st.chat_message("assistant" if role == "agent" else "user"):
            st.write(text)

    if ss.get("grill_complete"):
        st.success("All done — your quantified résumé is ready.")
        _offer_pdf()
        return

    if ss.get("grill_checkpoint"):
        with st.chat_message("assistant"):
            st.write("**Checkpoint — does this look right so far?**")
            st.write(ss["grill_checkpoint"])
        if st.button("Looks right — keep going", type="primary"):
            _confirm_checkpoint()
        return

    question = ss.get("grill_question")
    if question:
        with st.chat_message("assistant"):
            st.write(question)

    answer: Any = st.chat_input("Your answer…")
    if answer:
        _submit_answer(str(answer))
