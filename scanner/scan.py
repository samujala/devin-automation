"""CLI entrypoint and main scan flow."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from scanner.batches import assign_batches
from scanner.github_client import GitHubClient
from scanner.ruff_runner import run_ruff
from scanner.store import init_db, is_known, record_batch
from scanner.templates import render_issue_body


load_dotenv()

_RULES = ["UP007", "DTZ003"]


def _err(msg: str) -> None:
    click.echo(click.style(f"ERROR: {msg}", fg="red"), err=True)


def _info(msg: str) -> None:
    click.echo(msg)


def _dim(msg: str) -> None:
    click.echo(click.style(msg, dim=True))


@click.command()
@click.option(
    "--superset-path",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Path to the Superset repo to scan.",
)
@click.option(
    "--repo",
    default=lambda: os.environ.get("GITHUB_REPO", ""),
    show_default="$GITHUB_REPO",
    help="Target fork as owner/repo.",
)
@click.option(
    "--label",
    default="auto-remediable",
    show_default=True,
    help="Label to apply to filed issues.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would be filed without calling GitHub or writing to SQLite.",
)
@click.option(
    "--db-path",
    default="./data/findings.db",
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path to the SQLite database.",
)
def cli(
    superset_path: Path,
    repo: str,
    label: str,
    dry_run: bool,
    db_path: Path,
) -> None:
    """Scan Superset for UP007/DTZ003 violations and file GitHub issues."""

    token = os.environ.get("GITHUB_TOKEN", "")
    if not dry_run:
        if not token:
            _err("GITHUB_TOKEN is not set. Use --dry-run to skip GitHub calls.")
            sys.exit(1)
        if not repo:
            _err("--repo / GITHUB_REPO is not set.")
            sys.exit(1)

    # ── 1. Run ruff ────────────────────────────────────────────────────────
    _info(f"Scanning {superset_path} for {', '.join(_RULES)} …")
    findings = run_ruff(superset_path, _RULES)
    _info(f"  Found {len(findings)} findings (migrations excluded)\n")

    # ── 2. Group into batches ──────────────────────────────────────────────
    batches = assign_batches(findings)

    if not batches:
        _info("No findings — nothing to file.")
        return

    # ── 3. Initialise store ────────────────────────────────────────────────
    if not dry_run:
        init_db(db_path)

    # ── 4. GitHub client ───────────────────────────────────────────────────
    gh: GitHubClient | None = None
    if not dry_run:
        gh = GitHubClient(token=token, repo=repo)
        _dim(f"Ensuring label '{label}' exists on {repo} …")
        gh.ensure_label(label)

    # ── 5. Process each batch ──────────────────────────────────────────────
    filed = 0
    skipped = 0
    empty = 0

    _info(f"{'Batch':<32}  {'Count':>5}  {'Fingerprint':>16}  Status")
    _info("─" * 72)

    for batch in batches:
        if batch.count == 0:
            empty += 1
            _dim(f"{'[' + batch.key + ']':<32}  {'0':>5}  {'':>16}  (skipped — empty)")
            continue

        fingerprint = batch.fingerprint
        body = render_issue_body(batch)

        if not dry_run and is_known(db_path, fingerprint):
            skipped += 1
            status = click.style("already filed", fg="yellow")
            _info(f"{'[' + batch.key + ']':<32}  {batch.count:>5}  {fingerprint:>16}  {status}")
            continue

        if dry_run:
            status = click.style("would file", fg="cyan")
            _info(f"{'[' + batch.key + ']':<32}  {batch.count:>5}  {fingerprint:>16}  {status}")
            _dim(f"  Title: {batch.title}")
            _dim(f"  Label: {label}")
            _dim("  --- Issue body preview (first 10 lines) ---")
            for line in body.splitlines()[:10]:
                _dim(f"  {line}")
            _dim("  ---")
            filed += 1
            continue

        # Real filing
        assert gh is not None
        issue = gh.create_issue(title=batch.title, body=body, labels=[label])
        record_batch(
            db_path,
            batch,
            github_issue_number=issue.number,
            github_issue_url=issue.url,
        )
        filed += 1
        status = click.style(f"filed #{issue.number}", fg="green")
        _info(f"{'[' + batch.key + ']':<32}  {batch.count:>5}  {fingerprint:>16}  {status}")
        _dim(f"  {issue.url}")

    # ── 6. Summary ─────────────────────────────────────────────────────────
    _info("")
    if dry_run:
        _info(click.style(f"Dry run complete. {filed} batch(es) would be filed.", fg="cyan"))
    else:
        _info(
            click.style(
                f"Done. {filed} filed, {skipped} already known, {empty} empty (skipped).",
                fg="green",
            )
        )


if __name__ == "__main__":
    cli()
