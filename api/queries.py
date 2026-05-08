"""Pure SQL query functions. Each takes a sqlite3.Connection and returns plain dicts."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone


def get_metrics(conn: sqlite3.Connection) -> dict:
    r = conn.execute("SELECT SUM(finding_count) FROM batches").fetchone()
    total_findings = r[0] or 0

    issues_filed = conn.execute(
        "SELECT COUNT(*) FROM batches WHERE github_issue_number IS NOT NULL"
    ).fetchone()[0]

    sessions_started = conn.execute("SELECT COUNT(*) FROM devin_sessions").fetchone()[0]

    sessions_completed = conn.execute(
        "SELECT COUNT(*) FROM devin_sessions WHERE status = 'completed'"
    ).fetchone()[0]

    sessions_in_progress = conn.execute(
        "SELECT COUNT(*) FROM devin_sessions "
        "WHERE status NOT IN ('completed', 'failed', 'timeout', 'orphaned')"
    ).fetchone()[0]

    sessions_failed = conn.execute(
        "SELECT COUNT(*) FROM devin_sessions WHERE status IN ('failed', 'timeout')"
    ).fetchone()[0]

    prs_opened = conn.execute(
        "SELECT COUNT(*) FROM devin_sessions WHERE pr_url IS NOT NULL AND status = 'completed'"
    ).fetchone()[0]

    prs_merged = conn.execute(
        "SELECT COUNT(*) FROM devin_sessions WHERE merged_at IS NOT NULL"
    ).fetchone()[0]

    success_rate = None
    if sessions_completed > 0:
        success_rate = round(prs_opened / sessions_completed, 4)

    row = conn.execute(
        "SELECT AVG(duration_seconds), SUM(duration_seconds) "
        "FROM devin_sessions WHERE status = 'completed'"
    ).fetchone()
    avg_duration = int(row[0]) if row[0] is not None else None
    total_duration = int(row[1]) if row[1] is not None else 0

    estimated_acus = round(total_duration * 0.0067, 1)

    return {
        "total_findings": total_findings,
        "issues_filed": issues_filed,
        "sessions_started": sessions_started,
        "sessions_completed": sessions_completed,
        "sessions_in_progress": sessions_in_progress,
        "sessions_failed": sessions_failed,
        "prs_opened": prs_opened,
        "prs_merged": prs_merged,
        "success_rate": success_rate,
        "avg_duration_seconds": avg_duration,
        "total_duration_seconds": total_duration,
        "estimated_acus": estimated_acus,
    }


def get_throughput(conn: sqlite3.Connection, days: int = 14) -> list[dict]:
    today = datetime.now(tz=timezone.utc).date()
    date_list = [
        (today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)
    ]

    opened_rows = conn.execute(
        """
        SELECT
            DATE(finished_at) AS day,
            SUM(CASE WHEN pr_url IS NOT NULL THEN 1 ELSE 0 END) AS prs_opened,
            SUM(CASE WHEN status IN ('failed', 'timeout') THEN 1 ELSE 0 END) AS failed
        FROM devin_sessions
        WHERE finished_at IS NOT NULL
          AND DATE(finished_at) >= DATE('now', ?)
        GROUP BY DATE(finished_at)
        """,
        (f"-{days} days",),
    ).fetchall()

    merged_rows = conn.execute(
        """
        SELECT DATE(merged_at) AS day, COUNT(*) AS prs_merged
        FROM devin_sessions
        WHERE merged_at IS NOT NULL
          AND DATE(merged_at) >= DATE('now', ?)
        GROUP BY DATE(merged_at)
        """,
        (f"-{days} days",),
    ).fetchall()

    by_date: dict[str, dict] = {
        r[0]: {"prs_opened": r[1] or 0, "failed": r[2] or 0} for r in opened_rows
    }
    for r in merged_rows:
        by_date.setdefault(r[0], {"prs_opened": 0, "failed": 0})
        by_date[r[0]]["prs_merged"] = r[1] or 0

    return [
        {
            "date": d,
            "prs_opened": by_date.get(d, {}).get("prs_opened", 0),
            "prs_merged": by_date.get(d, {}).get("prs_merged", 0),
            "failed": by_date.get(d, {}).get("failed", 0),
        }
        for d in date_list
    ]


def get_live_sessions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            ds.devin_session_id,
            ds.devin_session_url,
            ds.status,
            ds.started_at,
            b.batch_key,
            b.rule,
            b.title
        FROM devin_sessions ds
        JOIN batches b ON ds.batch_fingerprint = b.fingerprint
        WHERE ds.status NOT IN ('completed', 'failed', 'timeout', 'orphaned')
        ORDER BY ds.started_at
        """
    ).fetchall()

    now = datetime.now(tz=timezone.utc)
    result = []
    for r in rows:
        started_raw = r[3]
        try:
            started = datetime.fromisoformat(started_raw)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = int((now - started).total_seconds())
        except Exception:
            elapsed = 0

        result.append(
            {
                "session_id": r[0],
                "session_url": r[1],
                "status": r[2],
                "status_enum": None,  # not stored in DB; populated by orchestrator at runtime
                "started_at": started_raw,
                "elapsed_seconds": elapsed,
                "batch_key": r[4],
                "rule": r[5],
                "title": r[6],
            }
        )
    return result


def get_recent_sessions(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            ds.devin_session_id,
            ds.pr_url,
            ds.pr_number,
            ds.duration_seconds,
            ds.finished_at,
            ds.merged_at,
            b.batch_key,
            b.rule,
            b.title
        FROM devin_sessions ds
        JOIN batches b ON ds.batch_fingerprint = b.fingerprint
        WHERE ds.status IN ('completed', 'failed', 'timeout', 'orphaned')
          AND ds.finished_at IS NOT NULL
        ORDER BY ds.finished_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    def _outcome(pr_url: str | None, merged_at: str | None) -> str:
        if merged_at:
            return "merged"
        if pr_url:
            return "success"
        return "failed"

    return [
        {
            "session_id": r[0],
            "pr_url": r[1],
            "pr_number": r[2],
            "duration_seconds": r[3],
            "finished_at": r[4],
            "merged_at": r[5],
            "batch_key": r[6],
            "rule": r[7],
            "title": r[8],
            "outcome": _outcome(r[1], r[5]),
        }
        for r in rows
    ]


def get_orchestrator_status(conn: sqlite3.Connection) -> dict:
    try:
        row = conn.execute(
            "SELECT started_at, last_poll_at, poll_count "
            "FROM orchestrator_heartbeat WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None  # table doesn't exist yet — orchestrator has never run

    if row is None:
        return {
            "is_alive": False,
            "last_poll_at": None,
            "started_at": None,
            "poll_count": 0,
            "seconds_since_poll": None,
        }

    now = datetime.now(tz=timezone.utc)
    try:
        last_poll = datetime.fromisoformat(row[1])
        if last_poll.tzinfo is None:
            last_poll = last_poll.replace(tzinfo=timezone.utc)
        seconds_since = int((now - last_poll).total_seconds())
        is_alive = seconds_since <= 75
    except Exception:
        seconds_since = None
        is_alive = False

    return {
        "is_alive": is_alive,
        "last_poll_at": row[1],
        "started_at": row[0],
        "poll_count": row[2],
        "seconds_since_poll": seconds_since,
    }


def get_failed_sessions(conn: sqlite3.Connection, days: int = 14) -> dict:
    rows = conn.execute(
        """
        SELECT
            ds.devin_session_id,
            ds.devin_session_url,
            ds.status,
            ds.duration_seconds,
            ds.finished_at,
            ds.error_message,
            b.batch_key,
            b.rule
        FROM devin_sessions ds
        JOIN batches b ON ds.batch_fingerprint = b.fingerprint
        WHERE ds.status IN ('failed', 'timeout', 'orphaned')
          AND (ds.finished_at IS NULL OR DATE(ds.finished_at) >= DATE('now', ?))
        ORDER BY ds.finished_at DESC
        """,
        (f"-{days} days",),
    ).fetchall()

    by_rule: dict[str, int] = {}
    detail = []
    for r in rows:
        rule = r[7]
        by_rule[rule] = by_rule.get(rule, 0) + 1

        status = r[2]
        duration = r[3]
        error = r[5]
        if status == "timeout":
            reason = f"timeout after {duration}s" if duration else "timeout"
        elif error:
            reason = error
        else:
            reason = status

        detail.append(
            {
                "session_id": r[0],
                "session_url": r[1],
                "batch_key": r[6],
                "rule": rule,
                "reason": reason,
                "finished_at": r[4],
            }
        )

    # Always return both rules
    by_rule_list = [
        {"rule": rule, "failed_count": by_rule.get(rule, 0)}
        for rule in ("DTZ003", "UP007")
    ]

    return {"by_rule": by_rule_list, "detail": detail}
