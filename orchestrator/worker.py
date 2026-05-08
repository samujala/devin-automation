"""Session lifecycle: spawn, poll, and finalize Devin sessions."""

from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.devin_client import DevinClient
from orchestrator.store import (
    BatchRow,
    SessionRow,
    append_event,
    count_in_progress_sessions,
    finalize_session,
    mark_batch_status,
    record_session_start,
    update_session,
)
from orchestrator.logging import log_event


def is_session_done(raw: dict) -> bool:
    """Return True when Devin has finished its current task.

    status_enum is the authoritative signal — status stays "running" forever.
    Secondary fallback: PR exists and agent is no longer actively working.
    """
    status_enum = raw.get("status_enum")
    pr = raw.get("pull_request")
    pr_url = pr.get("url") if isinstance(pr, dict) else None

    if status_enum in {"blocked", "finished", "stopped"}:
        return True
    if pr_url and status_enum != "working":
        return True
    return False


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _elapsed_seconds(started_at: str) -> int:
    try:
        start = datetime.fromisoformat(started_at)
        return int((datetime.now(tz=timezone.utc) - start).total_seconds())
    except Exception:
        return 0


def _extract_pr_number(pr_url: str | None) -> int | None:
    if not pr_url:
        return None
    m = re.search(r"/pull/(\d+)", pr_url)
    return int(m.group(1)) if m else None


def spawn_session(
    db_path: Path,
    client: DevinClient,
    batch: BatchRow,
    prompt: str,
    dry_run: bool = False,
) -> str | None:
    """Create a Devin session for *batch*, record it, return the session_id.

    Returns None if the concurrency cap is hit or on error.
    """
    if dry_run:
        log_event("dry_run_would_spawn", batch=batch.batch_key, prompt_chars=len(prompt))
        return None

    started_at = _now_iso()
    title = f"auto-fix/{batch.batch_key}"
    try:
        session = client.create_session(prompt=prompt, title=title)
    except Exception as exc:
        log_event("spawn_error", batch=batch.batch_key, error=str(exc))
        mark_batch_status(db_path, batch.fingerprint, "failed")
        append_event(db_path, "unknown", "spawn_error", {"error": str(exc), "batch": batch.batch_key})
        return None

    record_session_start(
        db_path,
        batch_fingerprint=batch.fingerprint,
        session_id=session.session_id,
        session_url=session.url,
        started_at=started_at,
    )
    mark_batch_status(db_path, batch.fingerprint, "in_progress")
    log_event(
        "session_started",
        batch=batch.batch_key,
        session_id=session.session_id,
        session_url=session.url,
    )
    append_event(
        db_path,
        session.session_id,
        "session_started",
        {"batch": batch.batch_key, "url": session.url},
    )
    return session.session_id


def poll_session(
    db_path: Path,
    client: DevinClient,
    session: SessionRow,
    timeout_seconds: int,
) -> bool:
    """Poll a running session and update the DB. Returns True if now terminal."""
    try:
        state = client.get_session(session.devin_session_id)
    except Exception as exc:
        log_event("poll_error", session_id=session.devin_session_id, error=str(exc))
        append_event(db_path, session.devin_session_id, "poll_error", {"error": str(exc)})
        return False

    elapsed = _elapsed_seconds(session.started_at)
    log_event(
        "session_status",
        session_id=session.devin_session_id,
        status=state.status,
        status_enum=state.status_enum,
        elapsed_s=elapsed,
    )

    # Check timeout first
    if elapsed >= timeout_seconds and not is_session_done(state.raw):
        _finalize(db_path, session, "timeout", elapsed, pr_url=state.pr_url)
        log_event("session_timeout", session_id=session.devin_session_id, elapsed_s=elapsed)
        return True

    pr_url = state.pr_url
    pr_number = _extract_pr_number(pr_url)

    if pr_url and not session.pr_url:
        log_event("pr_opened", session_id=session.devin_session_id, pr_url=pr_url)
        append_event(db_path, session.devin_session_id, "pr_opened", {"pr_url": pr_url})

    update_session(
        db_path,
        session_id=session.devin_session_id,
        status=state.status,
        pr_url=pr_url,
        pr_number=pr_number,
    )
    append_event(
        db_path,
        session.devin_session_id,
        "status_update",
        {"status": state.status, "status_enum": state.status_enum, "elapsed_s": elapsed},
    )

    if is_session_done(state.raw):
        outcome = "success" if pr_url else "failed"
        _finalize(db_path, session, outcome, elapsed, pr_url=pr_url)
        return True

    return False


def _finalize(
    db_path: Path,
    session: SessionRow,
    outcome: str,
    elapsed: int,
    pr_url: str | None = None,
) -> None:
    finished_at = _now_iso()
    # Map outcome → orchestrator terminal status
    status_map = {
        "success": "completed",
        "failed": "failed",
        "timeout": "timeout",
    }
    db_status = status_map.get(outcome, outcome)

    finalize_session(
        db_path,
        session_id=session.devin_session_id,
        status=db_status,
        finished_at=finished_at,
        duration_seconds=elapsed,
    )
    mark_batch_status(db_path, session.batch_fingerprint, db_status)
    log_event(
        "session_completed",
        session_id=session.devin_session_id,
        duration_s=elapsed,
        outcome=outcome,
        pr_url=pr_url,
    )
    append_event(
        db_path,
        session.devin_session_id,
        "session_completed",
        {"outcome": outcome, "duration_s": elapsed, "pr_url": pr_url},
    )


def orphan_in_progress_sessions(db_path: Path, sessions: list[SessionRow]) -> None:
    """Mark sessions as orphaned on SIGINT (don't cancel them — let Devin finish)."""
    for s in sessions:
        finalize_session(
            db_path,
            session_id=s.devin_session_id,
            status="orphaned",
            finished_at=_now_iso(),
            duration_seconds=_elapsed_seconds(s.started_at),
        )
        log_event("session_orphaned", session_id=s.devin_session_id)
