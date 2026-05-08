"""GitHub issue body builder."""

from __future__ import annotations

from datetime import datetime, timezone

from scanner.batches import Batch


_RULE_DESCRIPTIONS: dict[str, str] = {
    "UP007": "use `X | Y` instead of `Optional[X]` / `Union[X, Y]`",
    "DTZ003": "replace `datetime.utcnow()` with timezone-aware `datetime.now(tz=...)`",
}

# Per-batch instructions injected into the "What needs to be done" section.
_BATCH_INSTRUCTIONS: dict[str, str] = {
    "up007_utils": (
        "Replace all `Optional[X]` and `Union[X, Y]` type annotations in "
        "`superset/utils/` with the modern `X | Y` union syntax introduced in "
        "Python 3.10. This is a mechanical, purely syntactic change — no runtime "
        "behaviour is affected. Run `ruff check --select UP007 --fix superset/utils/` "
        "to apply automatically, then verify with `pytest tests/unit_tests/utils/`."
    ),
    "up007_commands": (
        "Replace all `Optional[X]` and `Union[X, Y]` type annotations in "
        "`superset/commands/` with the modern `X | Y` syntax. "
        "Apply with `ruff check --select UP007 --fix superset/commands/`, "
        "then verify with `pytest tests/unit_tests/commands/`."
    ),
    "up007_models_daos": (
        "Replace all `Optional[X]` and `Union[X, Y]` type annotations in "
        "`superset/models/` and `superset/daos/` with the modern `X | Y` syntax. "
        "Apply with `ruff check --select UP007 --fix superset/models/ superset/daos/`, "
        "then verify the affected unit tests."
    ),
    "up007_long_tail": (
        "Replace all remaining `Optional[X]` and `Union[X, Y]` type annotations "
        "across the codebase (files outside `utils/`, `commands/`, `models/`, and "
        "`daos/`) with the modern `X | Y` syntax. Each file can be fixed with "
        "`ruff check --select UP007 --fix <file>`. Note: `superset/migrations/` "
        "is intentionally excluded — do not modify migration files."
    ),
    "dtz003_cache_py": (
        "Replace `datetime.datetime.utcnow()` calls in `superset/utils/cache.py` "
        "with `datetime.datetime.now(tz=datetime.timezone.utc)`. "
        "This file uses the result for cache TTL calculations — confirm that any "
        "arithmetic on the returned value remains correct with a timezone-aware object."
    ),
    "dtz003_dates_py": (
        "Replace `datetime.datetime.utcnow()` calls in `superset/utils/dates.py` "
        "with `datetime.datetime.now(tz=datetime.timezone.utc)`. "
        "Review downstream consumers of functions in this module to ensure they "
        "handle timezone-aware datetimes correctly."
    ),
    "dtz003_log_py": (
        "Replace `datetime.datetime.utcnow()` calls in `superset/daos/log.py` "
        "with `datetime.datetime.now(tz=datetime.timezone.utc)`. "
        "This file writes log timestamps — verify the database column types "
        "accept timezone-aware values."
    ),
    "dtz003_execute_py": (
        "Replace `datetime.datetime.utcnow()` calls in "
        "`superset/commands/report/execute.py` with "
        "`datetime.datetime.now(tz=datetime.timezone.utc)`. "
        "**Important:** Several call sites in this file write `datetime.utcnow()` "
        "results directly to SQLAlchemy model fields (e.g., `last_eval_dttm` at "
        "line 130). Verify the model column definitions support tz-aware datetimes "
        "before applying the fix to those sites. If they don't, fix only the safe "
        "sites and comment on this issue explaining which sites need human review."
    ),
    "dtz003_other": (
        "Replace `datetime.datetime.utcnow()` calls in the remaining files listed "
        "below with `datetime.datetime.now(tz=datetime.timezone.utc)`. "
        "Review each call site individually to confirm that downstream code handles "
        "timezone-aware datetime objects correctly before submitting the fix."
    ),
}

_TABLE_MAX_ROWS = 30


def _findings_table(batch: Batch) -> str:
    rows = batch.findings[:_TABLE_MAX_ROWS]
    lines = [
        "| File | Line | Message |",
        "|------|------|---------|",
    ]
    for f in rows:
        lines.append(f"| `{f.file_path}` | {f.line_start} | `{f.message}` |")
    if batch.count > _TABLE_MAX_ROWS:
        overflow = batch.count - _TABLE_MAX_ROWS
        lines.append(f"| … | … | *…and {overflow} more* |")
    return "\n".join(lines)


def _test_path_hint(batch: Batch) -> str:
    """Best-effort pytest path for the batch's files."""
    prefixes = batch.spec.path_prefixes
    if not prefixes:
        return "pytest tests/unit_tests/"
    # Map the first source prefix to a likely test path
    src = prefixes[0].rstrip("/")
    # e.g. superset/utils -> tests/unit_tests/utils
    relative = src.replace("superset/", "", 1)
    return f"pytest tests/unit_tests/{relative}"


def render_issue_body(batch: Batch, timestamp: datetime | None = None) -> str:
    """Return the full Markdown body for the GitHub issue."""
    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc)

    rule_desc = _RULE_DESCRIPTIONS.get(batch.rule, batch.rule)
    instructions = _BATCH_INSTRUCTIONS.get(
        batch.key,
        "Apply the fix suggested by ruff and verify that existing tests still pass.",
    )
    scope = (
        ", ".join(f"`{p}`" for p in batch.spec.path_prefixes)
        if batch.spec.path_prefixes
        else "all remaining files for this rule"
    )
    test_hint = _test_path_hint(batch)

    return f"""\
## Auto-Remediation Task

**Rule:** `{batch.rule}` — {rule_desc}
**Scope:** {scope}
**Findings:** {batch.count}

## What needs to be done

{instructions}

## Findings detail

{_findings_table(batch)}

## Acceptance criteria

- All listed findings resolved
- No new ruff or mypy regressions in changed files
- Existing tests in affected modules pass: `{test_hint}`
- A single PR with a clear, scoped diff
- PR title format: `[auto-remediation] {batch.rule}: {batch.title}`

## How this issue was filed

Filed automatically by the auto-remediation scanner on \
{timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")}.
Fingerprint: `{batch.fingerprint}`
"""
