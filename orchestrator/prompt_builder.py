"""Build Devin prompts from batch data.

Each rule has its own template. The templates are derived from the manually
tested PR #10 structure which successfully produced an auto-remediation PR.
"""

from __future__ import annotations

from scanner.batches import Batch
from orchestrator.store import BatchRow


_UP007_TEMPLATE = """\
You are remediating a static analysis finding in a fork of Apache Superset.

REPOSITORY
- Fork: {repo_url}
- Base branch: master
- Working branch (you create this): auto-fix/{batch_key}

ISSUE TO REMEDIATE
- Issue URL: {issue_url}
- Issue title: {issue_title}
- Rule: UP007 — replace `Optional[X]` and `Union[X, Y]` with the modern `X | Y` PEP 604 syntax

WHAT YOU NEED TO DO

1. Clone the fork at {repo_url} and check out `master`.

2. Create a new branch: `auto-fix/{batch_key}`.

3. Apply ruff's autofix for UP007 to ONLY the files in scope:
   `ruff check {file_paths_space_separated} --select UP007 --fix`

4. The autofix is purely syntactic. It should not change behavior. Verify nothing else changed:
   `git diff --stat` — only the listed files should show changes.

5. Run `ruff check {file_paths_space_separated} --select UP007` to confirm zero remaining UP007 violations in scope.

6. Run the unit tests for the affected directories. Pick the most specific path that covers the changed files. Examples:
   `pytest tests/unit_tests/utils/ -x` (for utils-scoped batches)
   `pytest tests/unit_tests/commands/ -x` (for commands-scoped batches)
   If no specific test path matches, run `pytest tests/unit_tests/ -x -q` and capture the result.

7. If tests fail and the failure is caused by your change, fix it. Otherwise, do not touch unrelated files. Iterate up to 3 times.

8. If all tests pass and ruff is clean, commit with the message:
   `fix(UP007): modernize Optional types in {scope_description} (closes #{issue_number})`

9. Push the branch to the fork.

10. Open a pull request from `auto-fix/{batch_key}` to `master`. The PR title and body must follow:

    Title: [auto-remediation] UP007: modernize Optional types in {scope_description}

    Body:
    ## What
    Replaced `Optional[X]` and `Union[X, Y]` annotations with the modern `X | Y` syntax in {scope_description}.

    ## Why
    UP007 is enabled in this project's ruff config. Modern union syntax is preferred and these violations were unfixed.

    ## Validation
    - `ruff check {file_paths_space_separated} --select UP007` → clean
    - [pytest summary line, e.g., "47 passed in 8.3s"]

    ## Files changed
{file_paths_one_per_line}

    Closes #{issue_number}

CONSTRAINTS
- Do not modify any file outside the scope listed above.
- Do not bump dependency versions.
- Do not refactor unrelated code.
- If anything blocks completion, stop and post a comment on the issue with what's blocking.
- Do not merge the PR. Open it for review only.\
"""

_DTZ003_TEMPLATE = """\
You are remediating a static analysis finding in a fork of Apache Superset.

REPOSITORY
- Fork: {repo_url}
- Base branch: master
- Working branch (you create this): auto-fix/{batch_key}

ISSUE TO REMEDIATE
- Issue URL: {issue_url}
- Issue title: {issue_title}
- Rule: DTZ003 — replace `datetime.utcnow()` with timezone-aware `datetime.now(tz=timezone.utc)`

WHAT YOU NEED TO DO

1. Clone the fork at {repo_url} and check out `master`.

2. Create a new branch: `auto-fix/{batch_key}`.

3. For each file in scope ({file_paths_space_separated}), locate every `datetime.utcnow()` call.

4. For each call site, BEFORE making the change, determine how the returned datetime is used:
   a. Is it stored in a SQLAlchemy model field? Check the column definition. If the column is declared as `DateTime` without `timezone=True`, the change can break the write — DO NOT modify that site. Instead, comment on the issue explaining which line(s) need human review and skip them.
   b. Is it compared to or arithmetic'd with other datetime values? Check whether those other values are tz-aware or naive. A tz-aware vs. naive comparison raises TypeError at runtime.
   c. Is it returned from a function whose callers depend on a naive datetime?

5. For sites you determine are safe, replace `datetime.utcnow()` with `datetime.now(tz=timezone.utc)`. Add `from datetime import timezone` to the imports if not already present.

6. Run `ruff check {file_paths_space_separated} --select DTZ003` to see remaining violations. Some may remain (the ones you skipped) — that's OK if you have a justification.

7. Run the unit tests for the affected modules:
   `pytest tests/unit_tests/<relevant_path> -x`
   Discover the right test path by inspecting the repo structure if not obvious.

8. If tests fail because of your change, fix it. Iterate up to 3 times. If you cannot make tests pass, revert your changes for the failing site and continue with other sites.

9. Commit with: `fix(DTZ003): replace datetime.utcnow() in {scope_description} (closes #{issue_number})`

10. Push the branch and open a PR with this format:

    Title: [auto-remediation] DTZ003: replace datetime.utcnow() in {scope_description}

    Body:
    ## What
    Replaced `datetime.utcnow()` with `datetime.now(tz=timezone.utc)` in {scope_description}.

    ## Why
    `datetime.utcnow()` returns a naive datetime and is deprecated in Python 3.12. DTZ003 flags this.

    ## Validation
    - `ruff check {file_paths_space_separated} --select DTZ003` → [N remaining (intentionally skipped sites listed below)]
    - [pytest summary]

    ## Sites changed
    [list each site as file:line]

    ## Sites intentionally NOT changed (require human review)
    [if any — list with file:line and one-line reason]

    Closes #{issue_number}

CONSTRAINTS
- Do not modify any file outside the scope listed above.
- Do not bump dependency versions.
- It is BETTER to ship a partial fix with documented exclusions than to break the codebase. Err on the side of skipping risky sites.
- Do not merge the PR. Open it for review only.\
"""


def _scope_description(batch: Batch | BatchRow) -> str:
    """Short human-readable scope string, mirrors what's in the batch title."""
    if isinstance(batch, BatchRow):
        # Derive from title — strip the rule prefix
        title = batch.title
        for prefix in ("Modernize Optional types in ", "Replace `datetime.utcnow()` in "):
            if title.startswith(prefix):
                return title[len(prefix):]
        return title
    # Batch dataclass: use path_prefixes
    prefixes = batch.spec.path_prefixes
    if not prefixes:
        return "remaining files"
    return ", ".join(prefixes)


def _unique_file_paths(batch: Batch) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for f in batch.findings:
        if f.file_path not in seen:
            seen.add(f.file_path)
            result.append(f.file_path)
    return result


def build_prompt(batch: Batch, repo_url: str, issue_url: str) -> str:
    """Build the Devin prompt for a given batch. Picks the right template based on batch.rule."""
    file_paths = _unique_file_paths(batch)
    file_paths_space = " ".join(file_paths)
    file_paths_lines = "\n".join(f"    - `{p}`" for p in file_paths)
    issue_number = str(batch.spec.key)  # fallback

    # Try to parse issue number from URL
    if issue_url and "/" in issue_url:
        try:
            issue_number = issue_url.rstrip("/").split("/")[-1]
        except Exception:
            pass

    scope = _scope_description(batch)

    template = _UP007_TEMPLATE if batch.rule == "UP007" else _DTZ003_TEMPLATE
    return template.format(
        repo_url=repo_url,
        batch_key=batch.key,
        issue_url=issue_url,
        issue_title=batch.title,
        issue_number=issue_number,
        file_paths_space_separated=file_paths_space,
        file_paths_one_per_line=file_paths_lines,
        scope_description=scope,
    )


def build_prompt_from_row(
    batch_row: BatchRow,
    file_paths: list[str],
    repo_url: str,
) -> str:
    """Build a prompt from a BatchRow (used when Batch object not available)."""
    issue_url = batch_row.github_issue_url or ""
    issue_number = str(batch_row.github_issue_number or "")

    file_paths_space = " ".join(file_paths)
    file_paths_lines = "\n".join(f"    - `{p}`" for p in file_paths)
    scope = _scope_description(batch_row)

    template = _UP007_TEMPLATE if batch_row.rule == "UP007" else _DTZ003_TEMPLATE
    return template.format(
        repo_url=repo_url,
        batch_key=batch_row.batch_key,
        issue_url=issue_url,
        issue_title=batch_row.title,
        issue_number=issue_number,
        file_paths_space_separated=file_paths_space,
        file_paths_one_per_line=file_paths_lines,
        scope_description=scope,
    )
