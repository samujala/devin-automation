"""
One-shot script: query GitHub for every completed session with a pr_url and stamp
merged_at if the PR has been merged.

Usage:
    python scripts/sync_pr_status.py [--db-path data/findings.db] [--dry-run]

Reads GITHUB_TOKEN and GITHUB_REPO from the environment (or .env file).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import urllib.request
import urllib.error
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _check_pr_merged(token: str, owner: str, repo: str, pr_number: int) -> str | None:
    """Return the merged_at timestamp string if the PR is merged, else None."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for PR #{pr_number} — skipping")
        return None

    if data.get("merged") and data.get("merged_at"):
        return data["merged_at"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync PR merge status from GitHub")
    parser.add_argument("--db-path", default="data/findings.db")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't write")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        raise SystemExit("GITHUB_TOKEN and GITHUB_REPO must be set in the environment")

    owner, repo_name = repo.split("/", 1)

    db_path = Path(args.db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT devin_session_id, pr_url, pr_number
        FROM devin_sessions
        WHERE pr_url IS NOT NULL
          AND pr_number IS NOT NULL
          AND status = 'completed'
          AND merged_at IS NULL
        ORDER BY finished_at DESC
        """
    ).fetchall()

    if not rows:
        print("No unmerged PRs to check.")
        conn.close()
        return

    print(f"Checking {len(rows)} PR(s) against GitHub...")
    updated = 0

    for row in rows:
        pr_number = row["pr_number"]
        print(f"  PR #{pr_number} ({row['pr_url']}) ...", end=" ", flush=True)
        merged_at = _check_pr_merged(token, owner, repo_name, pr_number)
        if merged_at:
            print(f"merged at {merged_at}")
            if not args.dry_run:
                conn.execute(
                    "UPDATE devin_sessions SET merged_at = ? WHERE devin_session_id = ?",
                    (merged_at, row["devin_session_id"]),
                )
            updated += 1
        else:
            print("not merged")

    if not args.dry_run:
        conn.commit()
        print(f"\nStamped merged_at on {updated} session(s).")
    else:
        print(f"\n[dry-run] Would stamp {updated} session(s).")

    conn.close()


if __name__ == "__main__":
    main()
