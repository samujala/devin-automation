"""Invokes ruff and parses its JSON output into structured Finding objects."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel


class Finding(BaseModel):
    rule_id: str
    file_path: str  # relative to superset root, forward-slash separated
    line_start: int
    column_start: int | None
    message: str
    is_autofixable: bool


_AUTOFIXABLE_RULES: frozenset[str] = frozenset({"UP007"})
_MIGRATIONS_PREFIX = "superset/migrations/"


def run_ruff(superset_path: Path, rules: list[str]) -> list[Finding]:
    """Run ruff on *superset_path* for the given *rules* and return findings.

    Findings whose file path falls under superset/migrations/ are excluded.
    """
    # Resolve to absolute so relative_to() works regardless of cwd
    superset_path = superset_path.resolve()

    select = ",".join(rules)
    cmd = [
        "ruff",
        "check",
        "--select",
        select,
        "--output-format=json",
        "--no-fix",
        str(superset_path / "superset"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    # ruff exits 1 when it finds violations — that's expected
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"ruff exited {result.returncode}:\n{result.stderr}"
        )

    raw: list[dict] = json.loads(result.stdout or "[]")

    findings: list[Finding] = []
    for item in raw:
        # Normalise to a path relative to the superset repo root
        abs_path = item.get("filename", "")
        try:
            rel = Path(abs_path).relative_to(superset_path).as_posix()
        except ValueError:
            rel = abs_path

        if rel.startswith(_MIGRATIONS_PREFIX):
            continue

        code = item.get("code", "")
        location = item.get("location", {})
        fix = item.get("fix")

        findings.append(
            Finding(
                rule_id=code,
                file_path=rel,
                line_start=location.get("row", 0),
                column_start=location.get("column"),
                message=item.get("message", ""),
                is_autofixable=bool(fix) or code in _AUTOFIXABLE_RULES,
            )
        )

    return findings
