"""CLI entrypoint and main service loop for the orchestrator."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv

from orchestrator.devin_client import DevinClient
from orchestrator.logging import log_event, log_error
from orchestrator.poller import GitHubPoller
from orchestrator.prompt_builder import build_prompt_from_row
from orchestrator.store import (
    append_event,
    count_in_progress_sessions,
    get_all_batches_with_issues,
    get_batch_by_key,
    get_in_progress_sessions,
    get_unprocessed_batches,
    init_db,
    init_heartbeat,
    mark_batch_status,
    write_heartbeat,
)
from orchestrator.worker import orphan_in_progress_sessions, poll_session, spawn_session

load_dotenv()

_SHUTDOWN = False


def _handle_sigint(sig, frame) -> None:
    global _SHUTDOWN
    _SHUTDOWN = True
    click.echo("\nSIGINT received — stopping after current poll cycle.", err=True)


def _make_client() -> DevinClient:
    api_key = os.environ.get("DEVIN_API_KEY", "")
    base_url = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai/v1")
    if not api_key:
        click.echo("ERROR: DEVIN_API_KEY is not set.", err=True)
        sys.exit(1)
    return DevinClient(api_key=api_key, base_url=base_url)


def _get_file_paths_for_batch(db_path: Path, fingerprint: str) -> list[str]:
    """Load unique file paths from the findings table."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT file_path FROM findings WHERE batch_fingerprint = ? ORDER BY file_path",
            (fingerprint,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _probe(client: DevinClient) -> None:
    """Probe Devin API: create a session, poll twice, terminate, print raw JSON."""
    import json as _json
    import httpx

    api_key = os.environ.get("DEVIN_API_KEY", "")
    base = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai/v1")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(base_url=base, headers=headers, timeout=30.0) as http:
        print(f"\nPOST {base}/sessions ...")
        resp = http.post(
            "/sessions",
            json={"prompt": "Say hello and exit. Do not modify any code or files.", "title": "probe-test"},
        )
        print(f"Status: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        print(_json.dumps(data, indent=2))

        session_id = data["session_id"]
        print(f"\nSession ID: {session_id}")

        for i in range(2):
            time.sleep(3)
            print(f"\nGET {base}/sessions/{session_id} (poll {i+1}) ...")
            resp = http.get(f"/sessions/{session_id}")
            print(f"Status: {resp.status_code}")
            resp.raise_for_status()
            print(_json.dumps(resp.json(), indent=2))

        print(f"\nDELETE {base}/sessions/{session_id} ...")
        resp = http.delete(f"/sessions/{session_id}")
        print(f"Status: {resp.status_code}")
        if resp.content:
            print(resp.text)
        else:
            print("(empty body — 204 No Content)")

        print("\nProbe complete.")


def _print_prompts(db_path: Path, repo_url: str) -> None:
    """Print built prompts for all batches in the DB."""
    batches = get_all_batches_with_issues(db_path)
    if not batches:
        click.echo("No batches with GitHub issues found in DB.")
        return
    for batch in batches:
        file_paths = _get_file_paths_for_batch(db_path, batch.fingerprint)
        prompt = build_prompt_from_row(batch, file_paths, repo_url)
        click.echo(f"\n{'='*70}")
        click.echo(f"BATCH: {batch.batch_key}  (issue #{batch.github_issue_number})")
        click.echo("=" * 70)
        click.echo(prompt)


def _process_batch(
    db_path: Path,
    client: DevinClient,
    batch,
    issue_url: str,
    repo_url: str,
    dry_run: bool,
    max_concurrent: int,
) -> None:
    """Spawn a single Devin session for *batch*, respecting the concurrency cap."""
    if count_in_progress_sessions(db_path) >= max_concurrent:
        log_event("concurrency_cap_hit", batch=batch.batch_key, cap=max_concurrent)
        return

    file_paths = _get_file_paths_for_batch(db_path, batch.fingerprint)
    if not file_paths:
        log_event("skip_no_files", batch=batch.batch_key)
        return

    # Build a dummy Batch-like object for the prompt builder
    from orchestrator.prompt_builder import build_prompt_from_row
    prompt = build_prompt_from_row(batch, file_paths, repo_url)

    if dry_run:
        log_event(
            "dry_run_prompt",
            batch=batch.batch_key,
            issue_url=issue_url,
            prompt_chars=len(prompt),
            prompt_preview=prompt[:200],
        )
        mark_batch_status(db_path, batch.fingerprint, "queued")
        return

    mark_batch_status(db_path, batch.fingerprint, "queued")
    spawn_session(
        db_path=db_path,
        client=client,
        batch=batch,
        prompt=prompt,
        dry_run=False,
    )


@click.command()
@click.option("--repo", default=lambda: os.environ.get("GITHUB_REPO", ""), show_default="$GITHUB_REPO", help="owner/repo")
@click.option("--label", default="auto-remediable", show_default=True)
@click.option("--db-path", default="./data/findings.db", show_default=True, type=click.Path(path_type=Path))
@click.option("--dry-run", is_flag=True, help="Log prompts but don't call Devin's API.")
@click.option("--only-batch", default=None, metavar="BATCH_KEY", help="Process this one batch and exit.")
@click.option("--probe-only", is_flag=True, help="Verify Devin API connectivity and exit.")
@click.option("--print-prompts", "print_prompts", is_flag=True, help="Print prompts for all batches and exit.")
def cli(
    repo: str,
    label: str,
    db_path: Path,
    dry_run: bool,
    only_batch: str | None,
    probe_only: bool,
    print_prompts: bool,
) -> None:
    """Orchestrate Devin sessions for auto-remediable GitHub issues."""

    devin_dry_run = dry_run or os.environ.get("DEVIN_DRY_RUN", "false").lower() == "true"

    poll_github = int(os.environ.get("POLL_INTERVAL_GITHUB_SECONDS", "60"))
    poll_devin = int(os.environ.get("POLL_INTERVAL_DEVIN_SECONDS", "30"))
    max_concurrent = int(os.environ.get("MAX_CONCURRENT_SESSIONS", "3"))
    timeout_seconds = int(os.environ.get("SESSION_TIMEOUT_SECONDS", "1800"))

    # ── --probe-only — no --repo needed ──────────────────────────────────────
    if probe_only:
        client = _make_client()
        _probe(client)
        return

    if not repo:
        click.echo("ERROR: --repo / GITHUB_REPO is not set.", err=True)
        sys.exit(1)

    repo_url = f"https://github.com/{repo}"

    # ── --print-prompts ───────────────────────────────────────────────────────
    if print_prompts:
        init_db(db_path)
        _print_prompts(db_path, repo_url)
        return

    # ── --only-batch ──────────────────────────────────────────────────────────
    if only_batch:
        init_db(db_path)
        batch = get_batch_by_key(db_path, only_batch)
        if not batch:
            click.echo(f"ERROR: batch '{only_batch}' not found in DB.", err=True)
            sys.exit(1)

        client = _make_client() if not devin_dry_run else None

        file_paths = _get_file_paths_for_batch(db_path, batch.fingerprint)
        prompt = build_prompt_from_row(batch, file_paths, repo_url)

        if devin_dry_run:
            log_event(
                "dry_run_prompt",
                batch=batch.batch_key,
                prompt_chars=len(prompt),
                prompt_preview=prompt[:200],
            )
            click.echo("\n" + prompt)
            return

        assert client is not None
        session_id = spawn_session(db_path, client, batch, prompt, dry_run=False)
        if not session_id:
            click.echo("Spawn failed — see logs above.", err=True)
            sys.exit(1)

        click.echo(f"Session started: {session_id}")
        click.echo("Polling until terminal state...")

        while True:
            time.sleep(poll_devin)
            sessions = get_in_progress_sessions(db_path)
            running = [s for s in sessions if s.devin_session_id == session_id]
            if not running:
                click.echo("Session no longer in-progress.")
                break
            done = poll_session(db_path, client, running[0], timeout_seconds)
            if done:
                break
        return

    # ── Main service loop ─────────────────────────────────────────────────────
    signal.signal(signal.SIGINT, _handle_sigint)

    init_db(db_path)
    init_heartbeat(db_path)
    client = _make_client() if not devin_dry_run else None

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        click.echo("ERROR: GITHUB_TOKEN is not set.", err=True)
        sys.exit(1)

    poller = GitHubPoller(token=github_token, repo=repo, label=label)

    log_event(
        "orchestrator_started",
        repo=repo,
        dry_run=devin_dry_run,
        max_concurrent=max_concurrent,
        timeout_seconds=timeout_seconds,
    )

    # Resume any sessions that were in-progress before restart
    resumed = get_in_progress_sessions(db_path)
    if resumed:
        log_event("resuming_sessions", count=len(resumed), session_ids=[s.devin_session_id for s in resumed])

    last_github_poll = 0.0

    while not _SHUTDOWN:
        write_heartbeat(db_path)
        now = time.monotonic()

        # ── Poll Devin for running sessions ───────────────────────────────
        if client:
            running = get_in_progress_sessions(db_path)
            for s in running:
                try:
                    poll_session(db_path, client, s, timeout_seconds)
                except Exception as exc:
                    log_error("poll_session_error", exc, session_id=s.devin_session_id)
                    append_event(db_path, s.devin_session_id, "poll_error", {"error": str(exc)})

        # ── Poll GitHub for new issues ─────────────────────────────────────
        if now - last_github_poll >= poll_github:
            last_github_poll = now
            try:
                new_work = poller.find_new_work(db_path)
                log_event("github_poll", new_issues=len(new_work))
                for work in new_work:
                    if _SHUTDOWN:
                        break
                    if count_in_progress_sessions(db_path) >= max_concurrent:
                        log_event("concurrency_cap_hit", cap=max_concurrent)
                        break
                    try:
                        _process_batch(
                            db_path=db_path,
                            client=client,
                            batch=work.batch,
                            issue_url=work.issue_url,
                            repo_url=repo_url,
                            dry_run=devin_dry_run,
                            max_concurrent=max_concurrent,
                        )
                    except Exception as exc:
                        log_error("process_batch_error", exc, batch=work.batch.batch_key)
            except Exception as exc:
                log_error("github_poll_error", exc)

        if _SHUTDOWN:
            break

        time.sleep(poll_devin)

    # ── Shutdown: orphan in-flight sessions ───────────────────────────────
    in_flight = get_in_progress_sessions(db_path)
    if in_flight:
        log_event("orphaning_sessions", count=len(in_flight))
        orphan_in_progress_sessions(db_path, in_flight)

    log_event("orchestrator_stopped")


if __name__ == "__main__":
    cli()
