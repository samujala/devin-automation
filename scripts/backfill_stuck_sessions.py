"""Finalize any DB sessions that are stuck in a non-terminal state but are actually done.

Run with:
    python scripts/backfill_stuck_sessions.py

Requires DEVIN_API_KEY in .env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.devin_client import DevinClient
from orchestrator.store import (
    get_in_progress_sessions,
    finalize_session,
    mark_batch_status,
    append_event,
)
from orchestrator.worker import is_session_done, _elapsed_seconds, _extract_pr_number, _now_iso

DB_PATH = Path(__file__).parent.parent / "data" / "findings.db"
API_KEY = os.environ.get("DEVIN_API_KEY", "")
BASE_URL = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai/v1")

if not API_KEY:
    print("ERROR: DEVIN_API_KEY not set.", file=sys.stderr)
    sys.exit(1)

client = DevinClient(api_key=API_KEY, base_url=BASE_URL)
sessions = get_in_progress_sessions(DB_PATH)

if not sessions:
    print("No non-terminal sessions in DB.")
    sys.exit(0)

print(f"Found {len(sessions)} non-terminal session(s). Checking with Devin API...\n")

for s in sessions:
    print(f"  {s.devin_session_id}  (batch: {s.batch_fingerprint})")
    try:
        state = client.get_session(s.devin_session_id)
    except Exception as exc:
        print(f"    ERROR fetching session: {exc}")
        continue

    print(f"    status={state.status!r}  status_enum={state.status_enum!r}  pr_url={state.pr_url!r}")

    if not is_session_done(state.raw):
        print("    → still running, skipping")
        continue

    elapsed = _elapsed_seconds(s.started_at)
    pr_url = state.pr_url
    pr_number = _extract_pr_number(pr_url)
    outcome = "success" if pr_url else "failed"
    db_status = "completed" if outcome == "success" else "failed"
    finished_at = _now_iso()

    finalize_session(DB_PATH, s.devin_session_id, db_status, finished_at, elapsed)
    mark_batch_status(DB_PATH, s.batch_fingerprint, db_status)
    append_event(DB_PATH, s.devin_session_id, "backfill_finalized", {
        "outcome": outcome,
        "pr_url": pr_url,
        "pr_number": pr_number,
        "duration_s": elapsed,
    })

    print(f"    → finalized as {db_status} (pr_url={pr_url}, duration={elapsed}s)")

print("\nDone.")
