"""Interactive "Grill Me" chat for the web workspace (Phase 2A web grill).

Drives the SAME turn-based discovery graph the CLI uses (``DiscoverySession``),
rendered as a Streamlit chat. Bring-your-own-key (BYOK): the user pastes their own
Gemini API key so grilling runs on THEIR quota (no shared platform key, no
free-tier bottleneck) — consistent with the privacy-first design (ARCHITECTURE §5).

Persistence: the discovery session is backed by ``FirestoreSessionService`` under a
STABLE per-user session id (:func:`web.session_loader.web_session_id`), so grilling
is durable — it survives reruns, restarts, and redeploys, shows up in the Portfolio
view + progress meter (which read the same session), and resumes where the user left
off. Transient UI bits (the live ``DiscoverySession`` object, the chat transcript,
the current question, the BYOK key) live in ``st.session_state``; the key is never
persisted to the session (BYOK stays in Secret Manager only).

Note: the discovery nodes resolve their model client from a process-global factory
(``workflows.nodes``), so this UI targets ONE user per server instance — fine for
the single-user demo (Cloud Run is pinned to one instance).
"""

from __future__ import annotations

import pathlib
import tempfile
from datetime import date
from typing import Any

import streamlit as st
from google.adk.sessions import BaseSessionService, InMemorySessionService

from auth.key_vault import SecretManagerKeyVault
from cli import session as session_helpers
from cli.app import (
    DiscoverySession,
    TurnResult,
    build_session_service,
    guess_resume_mime,
)
from config import AccessMode, get_settings
from database.firestore_session import ContractVersionError
from integration.model_client import GeminiModelClient, ModelAPIError
from schema import CareerEngineState, Entry, EntryStatus, PhaseStatus
from web.async_runner import run_async
from web.session_loader import web_session_id

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


@st.cache_resource(show_spinner=False)
def _grill_session_service() -> BaseSessionService:
    """Cached Firestore-backed session service (identity-agnostic → safe to share).

    Cached across reruns so the grill doesn't churn a new async Firestore client on
    every interaction / resume attempt. ``build_session_service`` falls back to
    in-memory (LOUD on stderr) only if Firestore is unreachable.
    """
    return build_session_service(use_firestore=True)


def _discovery_session(user_id: str, client: GeminiModelClient) -> DiscoverySession:
    """Build a DiscoverySession backed by durable Firestore state (stable per-user id).

    BYOK: the user brought their own key, so reasoning-heavy extraction routes to
    Pro (via the registry, when ACCESS_MODE=BYOK) for stronger understanding — the
    conversational/bulk steps stay on Flash/Flash-Lite for cost. The app_name +
    session_id match what the Portfolio view / meter / add-experience seam read, so
    it's ONE resumable session per user.
    """
    return DiscoverySession(
        user_id=user_id,
        access_mode=AccessMode.BYOK,
        model_client=client,
        session_service=_grill_session_service(),
        app_name=get_settings().app_name,
        session_id=web_session_id(user_id),
    )


def _grill_ids(user_id: str) -> dict[str, Any]:
    """The (service, app_name, user_id, session_id) addressing the durable session."""
    return {
        "session_service": _grill_session_service(),
        "app_name": get_settings().app_name,
        "user_id": user_id,
        "session_id": web_session_id(user_id),
    }


def _frontier_label(state: CareerEngineState) -> str:
    """Human label for the experience currently being grilled (grill_frontier), or ''."""
    fid = state.grill_frontier
    if not fid:
        return ""
    entry = next((e for e in state.work_timeline if str(e.entry_id) == fid), None)
    if entry is None:
        return ""
    parts = [entry.title or "this experience"]
    if entry.org:
        parts.append(entry.org)
    return " · ".join(parts)


_TRANSCRIPT_MAX_MESSAGES = 40  # keep the recent tail (bounds Firestore doc size)
_TRANSCRIPT_MAX_CHARS = 2000  # per message (a pasted wall of text can't bloat the doc)


def _persist_transcript(user_id: str) -> None:
    """Persist a BOUNDED chat transcript into the durable session (best-effort).

    Stored under a non-contract ADK session-state key so a returning user sees
    prior context on resume. The transcript shares the session document, so it is
    capped (recent tail + per-message length) to stay well under Firestore's 1 MiB
    doc limit — an unbounded transcript could otherwise fail core workflow writes.
    Persisted as plain [role, text] lists (Firestore-safe). Never blocks a turn.
    """
    transcript = st.session_state.get("grill_transcript", [])
    bounded = [
        [str(role), str(text)[:_TRANSCRIPT_MAX_CHARS]]
        for role, text in transcript[-_TRANSCRIPT_MAX_MESSAGES:]
    ]
    try:
        run_async(session_helpers.patch_state(**_grill_ids(user_id), _ui_transcript=bounded))
    except Exception:
        pass


def _start_session(
    user_id: str, history: str, work_timeline: list[Entry] | None = None
) -> None:
    """Create a DiscoverySession on the BYOK key and run the opening turn.

    ``work_timeline`` seeds pre-parsed entries (résumé vision ingest) instead of
    parsing ``history`` text. ``start`` is last-write-wins on the stable session id,
    so this cleanly (re)starts a fresh durable session.
    """
    ss = st.session_state
    ss.pop("grill_start_fresh", None)  # committing to a new session
    client = GeminiModelClient(api_key=ss["grill_key"])
    session = _discovery_session(user_id, client)
    try:
        with st.spinner("Reading your history and preparing the first question…"):
            question = run_async(
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
    ss["grill_entry_label"] = _frontier_label(run_async(session.current_state()))
    st.rerun()


def _migrate_education_on_resume(user_id: str, state: CareerEngineState) -> CareerEngineState:
    """Retroactively apply the 'education is not job-grilled' rule to an old session.

    Sessions parsed before that rule shipped still have EDUCATION entries queued as
    NEEDS_QUANTIFYING (and possibly pinned as the frontier), so the grill demands
    job metrics from a diploma. Re-run the status rules here (idempotent: only
    EDUCATION → SUMMARIZED changes) and clear a frontier that now points at a
    non-grillable entry, so the durable session self-heals without a re-upload.
    """
    from workflows.nodes import _apply_entry_status_rules

    migrated = [e.model_copy() for e in state.work_timeline]
    before = [e.status for e in migrated]
    # Use the session's injected clock so the migration is stable/idempotent across
    # days (contract: nodes treat reference_date as "now", never datetime.now()).
    ref_date = state.reference_date or date.today().isoformat()
    _apply_entry_status_rules(migrated, ref_date)
    if [e.status for e in migrated] == before and not _frontier_needs_reset(state, migrated):
        return state  # nothing to heal

    frontier = state.grill_frontier
    frontier_entry = next((e for e in migrated if str(e.entry_id) == frontier), None)
    if frontier_entry is None or frontier_entry.status not in (
        EntryStatus.NEEDS_QUANTIFYING,
        EntryStatus.DOCUMENTED,
    ):
        frontier = ""  # pinned entry is no longer grillable → let the graph re-pick

    try:
        run_async(
            session_helpers.patch_state(
                **_grill_ids(user_id),
                work_timeline=[e.model_dump(mode="json") for e in migrated],
                grill_frontier=frontier,
            )
        )
    except Exception:
        return state  # best-effort; fall back to the unmigrated state
    return state.model_copy(update={"work_timeline": migrated, "grill_frontier": frontier})


def _frontier_needs_reset(state: CareerEngineState, migrated: list[Entry]) -> bool:
    """True if grill_frontier points at an entry that is no longer grillable."""
    if not state.grill_frontier:
        return False
    entry = next((e for e in migrated if str(e.entry_id) == state.grill_frontier), None)
    return entry is None or entry.status not in (
        EntryStatus.NEEDS_QUANTIFYING,
        EntryStatus.DOCUMENTED,
    )


def _try_resume(user_id: str) -> None:
    """Rebuild the durable session from Firestore and restore the UI (if one exists).

    Called when there's no live DiscoverySession in this browser session (fresh
    tab, restart, or redeploy). The grilling STATE lives in Firestore, so we
    reconstruct the (cheap) session object and re-derive what to show. A brand-new
    user with no prior session is a no-op → the seeding UI is shown.
    """
    ss = st.session_state
    key = ss.get("grill_key")
    if not key:
        return
    client = GeminiModelClient(api_key=key)
    session = _discovery_session(user_id, client)
    # One raw read gives us both the CareerEngineState (flat) AND the persisted UI
    # transcript (a non-contract key), so a returning user sees prior context.
    try:
        raw = run_async(session_helpers.read_raw_state(**_grill_ids(user_id)))
    except ContractVersionError:
        st.warning(
            "Your saved session was created by an incompatible version and can't be "
            "resumed. You can start a new one below."
        )
        return
    except ValueError:
        return  # no session persisted yet → show the seeding UI
    except Exception:
        # Backend hiccup — don't crash; make the failure visible and let it retry.
        st.warning("Couldn't load your saved session just now — you can keep going or retry.")
        return
    state = CareerEngineState.model_validate(raw)
    if not (state.work_timeline or state.question_count):
        return  # nothing meaningful to resume

    state = _migrate_education_on_resume(user_id, state)

    ss["grill_client"] = client
    ss["grill_session"] = session
    ss["grill_transcript"] = [tuple(pair) for pair in (raw.get("_ui_transcript") or [])]
    ss["grill_entry_label"] = _frontier_label(state)
    ss["grill_started"] = True
    ss["grill_resumed"] = True
    if state.current_phase == PhaseStatus.COMPLETE:
        ss["grill_complete"] = True
        ss["grill_question"] = ""
        ss["grill_checkpoint"] = ""
    elif state.checkpoint_delta_summary and not state.checkpoint_verified:
        ss["grill_checkpoint"] = state.checkpoint_delta_summary
        ss["grill_question"] = ""
    else:
        ss["grill_checkpoint"] = ""
        ss["grill_question"] = state.current_question or _METRIC_NUDGE


def _submit_answer(answer: str, user_id: str) -> None:
    """Record an answer, run a turn, and drive any non-interactive turns."""
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    ss["grill_transcript"].append(("agent", ss.get("grill_question", "")))
    ss["grill_transcript"].append(("user", answer))
    try:
        with st.spinner("Thinking…"):
            before = run_async(session.current_state())
            turn = run_async(session.answer(answer))
            after = run_async(session.current_state())
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
                    turn = run_async(session.advance())
            # Refresh the "currently grilling" label from the (possibly advanced) state.
            label_state = run_async(session.current_state()) if accepted else after
            ss["grill_entry_label"] = _frontier_label(label_state)
    except ModelAPIError as exc:
        _show_model_error(exc)
        return
    _apply_turn(turn)
    _persist_transcript(user_id)
    st.rerun()


def _apply_pending_jump(user_id: str) -> None:
    """Handle a 'Grill me about this' jump from the Portfolio view.

    The Portfolio button sets ``grill_jump_to`` (an entry_id) + routes here. We pin
    the frontier to that entry and run a turn so the grill actually asks about IT —
    otherwise a live in-browser session would keep showing the previous question.
    Builds a session first if the jump arrived without one (e.g. straight from
    Portfolio without having grilled in this browser session yet).
    """
    ss = st.session_state
    target = ss.get("grill_jump_to")
    key = ss.get("grill_key")
    if not target or not key:
        ss.pop("grill_jump_to", None)
        return
    client = ss.get("grill_client") or GeminiModelClient(api_key=key)
    session = ss.get("grill_session") or _discovery_session(user_id, client)
    try:
        with st.spinner("Switching to that experience…"):
            run_async(
                session_helpers.patch_state(
                    **_grill_ids(user_id), grill_frontier=target, pending_user_answer=""
                )
            )
            turn = run_async(session.advance())
            ss["grill_entry_label"] = _frontier_label(run_async(session.current_state()))
    except ModelAPIError as exc:
        _show_model_error(exc)
        ss.pop("grill_jump_to", None)
        return
    ss["grill_client"] = client
    ss["grill_session"] = session
    ss.setdefault("grill_transcript", [])
    ss["grill_started"] = True
    ss["grill_checkpoint"] = ""
    ss["grill_complete"] = False
    ss.pop("grill_jump_to", None)
    _apply_turn(turn)
    _persist_transcript(user_id)
    st.rerun()


def _skip_entry(user_id: str) -> None:
    """Skip the current experience (mark SKIPPED), advance, and ask the next opener.

    The escape hatch for anything that shouldn't be metric-grilled — a course, a
    credential, or just something the user doesn't want to detail.
    """
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    label = ss.get("grill_entry_label") or "this experience"
    try:
        with st.spinner("Moving on…"):
            state = run_async(session.current_state())
            fid = state.grill_frontier
            new_timeline = [
                e.model_copy(update={"status": EntryStatus.SKIPPED})
                if str(e.entry_id) == fid
                else e
                for e in state.work_timeline
            ]
            # Mark skipped, clear the frontier (graph auto-picks the next needs-work
            # entry), and drop any pending answer so we get a fresh opening question.
            run_async(
                session_helpers.patch_state(
                    **_grill_ids(user_id),
                    work_timeline=[e.model_dump(mode="json") for e in new_timeline],
                    grill_frontier="",
                    pending_user_answer="",
                )
            )
            turn = run_async(session.advance())
            ss["grill_entry_label"] = _frontier_label(run_async(session.current_state()))
    except ModelAPIError as exc:
        _show_model_error(exc)  # nothing recorded yet → no false "skipped" line to undo
        return
    # Only record the skip once the state change actually succeeded.
    ss["grill_transcript"].append(("user", f"(skipped {label})"))
    _apply_turn(turn)
    _persist_transcript(user_id)
    st.rerun()


def _confirm_checkpoint(user_id: str) -> None:
    """Confirm the checkpoint and continue grilling."""
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    ss["grill_transcript"].append(("agent", f"[checkpoint] {ss.get('grill_checkpoint', '')}"))
    ss["grill_transcript"].append(("user", "Looks right — keep going."))
    try:
        with st.spinner("Continuing…"):
            question = run_async(session.confirm_checkpoint())
            ss["grill_entry_label"] = _frontier_label(run_async(session.current_state()))
    except ModelAPIError as exc:
        _show_model_error(exc)
        return
    ss["grill_checkpoint"] = ""
    ss["grill_question"] = question
    _persist_transcript(user_id)
    st.rerun()


def _offer_pdf() -> None:
    """Render the completed résumé to a downloadable PDF."""
    ss = st.session_state
    session: DiscoverySession = ss["grill_session"]
    if st.button("Generate résumé PDF", type="primary"):
        try:
            with st.spinner("Rendering your résumé…"):
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    out = run_async(session.render_resume_pdf(pathlib.Path(tf.name)))
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
    """Clear local grill UI state and mark intent to start fresh (non-destructive).

    Keeps the BYOK key (so it needn't be re-entered) and does NOT delete the durable
    Firestore session — the existing portfolio stays intact until the user actually
    starts a new grill, which overwrites it (last-write-wins on the stable id).
    ``grill_start_fresh`` suppresses auto-resume so the seeding UI is shown.
    """
    keep = {"grill_key", "grill_key_persisted"}
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("grill_") and k not in keep:
            del st.session_state[k]
    st.session_state["grill_start_fresh"] = True


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

    # Durability guard: if storage fell back to in-memory, grilling won't be saved
    # or resumable — say so plainly rather than silently losing progress later.
    if isinstance(_grill_session_service(), InMemorySessionService):
        st.warning(
            "⚠️ Saved storage is unavailable right now, so this grill **won't be saved "
            "or resumable** — your progress may be lost if you leave. Try again shortly."
        )

    # ── "Grill me about this" jump from the Portfolio view ────────────────────
    if ss.get("grill_jump_to"):
        _apply_pending_jump(user_id)

    # ── Resume a durable session across reruns / restarts / redeploys ─────────
    # If we have the key but no live session object in this browser session, try
    # to rebuild it from Firestore. Skipped right after "Restart" (grill_start_fresh).
    if (
        "grill_session" not in ss
        and not ss.get("grill_started")
        and not ss.get("grill_start_fresh")
    ):
        _try_resume(user_id)

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
    if ss.pop("grill_resumed", False):
        st.caption("↩︎ Picked up your saved session where you left off.")

    # Which experience are we grilling right now? (grill_frontier → entry label)
    if not ss.get("grill_complete") and ss.get("grill_entry_label"):
        st.info(f"📌 Currently grilling: **{ss['grill_entry_label']}**")

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
            _confirm_checkpoint(user_id)
        return

    question = ss.get("grill_question")
    if not question:
        # Never strand the user with no prompt (e.g. after a topic change the model
        # returned an empty follow-up) — ask an entry-aware opener, not a generic nudge.
        label = ss.get("grill_entry_label") or "this experience"
        question = (
            f"Let's dig into **{label}** — what's a specific accomplishment there "
            "you're proud of, and what impact did it have?"
        )
        ss["grill_question"] = question
    with st.chat_message("assistant"):
        st.write(question)

    # Escape hatch: move past an entry that shouldn't be metric-grilled (a course /
    # credential) or that the user doesn't want to detail.
    if st.button("Skip this experience →"):
        _skip_entry(user_id)

    answer: Any = st.chat_input("Your answer…")
    if answer:
        _submit_answer(str(answer), user_id)
