"""Encodes the 8-batch portfolio rules and groups raw findings into batches."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from scanner.ruff_runner import Finding


@dataclass
class BatchSpec:
    """Static definition of one remediation batch."""

    key: str
    title: str
    rule: str
    # Each element is either an exact file path (prefix match off) or a glob
    # prefix (ends with /). Matching is done against finding.file_path.
    path_prefixes: list[str]
    # If True, this batch is a catch-all for its rule (after earlier batches
    # have claimed their findings). Exactly one catch-all per rule allowed.
    is_catch_all: bool = False


# Order matters: earlier specs have priority. Catch-all is always last.
BATCH_SPECS: list[BatchSpec] = [
    # ── UP007 batches ────────────────────────────────────────────────────────
    BatchSpec(
        key="up007_utils",
        title="Modernize Optional types in `superset/utils/`",
        rule="UP007",
        path_prefixes=["superset/utils/"],
    ),
    BatchSpec(
        key="up007_commands",
        title="Modernize Optional types in `superset/commands/`",
        rule="UP007",
        path_prefixes=["superset/commands/"],
    ),
    BatchSpec(
        key="up007_models_daos",
        title="Modernize Optional types in `superset/models/` and `superset/daos/`",
        rule="UP007",
        path_prefixes=["superset/models/", "superset/daos/"],
    ),
    BatchSpec(
        key="up007_long_tail",
        title="Modernize Optional types — long tail",
        rule="UP007",
        path_prefixes=[],
        is_catch_all=True,
    ),
    # ── DTZ003 batches ───────────────────────────────────────────────────────
    BatchSpec(
        key="dtz003_cache_py",
        title="Replace `datetime.utcnow()` in `superset/utils/cache.py`",
        rule="DTZ003",
        path_prefixes=["superset/utils/cache.py"],
    ),
    BatchSpec(
        key="dtz003_dates_py",
        title="Replace `datetime.utcnow()` in `superset/utils/dates.py`",
        rule="DTZ003",
        path_prefixes=["superset/utils/dates.py"],
    ),
    BatchSpec(
        key="dtz003_log_py",
        title="Replace `datetime.utcnow()` in `superset/daos/log.py`",
        rule="DTZ003",
        path_prefixes=["superset/daos/log.py"],
    ),
    BatchSpec(
        key="dtz003_execute_py",
        title="Replace `datetime.utcnow()` in `superset/commands/report/execute.py`",
        rule="DTZ003",
        path_prefixes=["superset/commands/report/execute.py"],
    ),
    # Catch-all: any DTZ003 findings not claimed by the four explicit batches above
    BatchSpec(
        key="dtz003_other",
        title="Replace `datetime.utcnow()` — remaining files",
        rule="DTZ003",
        path_prefixes=[],
        is_catch_all=True,
    ),
]


@dataclass
class Batch:
    """A resolved batch — spec + the actual findings assigned to it."""

    spec: BatchSpec
    findings: list[Finding] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def title(self) -> str:
        return self.spec.title

    @property
    def rule(self) -> str:
        return self.spec.rule

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def fingerprint(self) -> str:
        raw = f"{self.rule}|{self.key}|{self.count}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _finding_matches_spec(finding: Finding, spec: BatchSpec) -> bool:
    """True if *finding* belongs to *spec* (ignoring catch-all logic)."""
    if finding.rule_id != spec.rule:
        return False
    return any(finding.file_path.startswith(prefix) for prefix in spec.path_prefixes)


def assign_batches(findings: list[Finding]) -> list[Batch]:
    """Assign each finding to exactly one Batch and return all non-empty batches.

    Priority: earlier specs win. Catch-all specs absorb whatever remains for
    their rule. Findings under superset/migrations/ must already be excluded
    by the caller (ruff_runner does this).
    """
    batches: dict[str, Batch] = {spec.key: Batch(spec=spec) for spec in BATCH_SPECS}

    # Track which findings have been claimed
    claimed: set[int] = set()

    # First pass: assign to concrete (non-catch-all) specs in priority order
    for spec in BATCH_SPECS:
        if spec.is_catch_all:
            continue
        batch = batches[spec.key]
        for i, finding in enumerate(findings):
            if i in claimed:
                continue
            if _finding_matches_spec(finding, spec):
                batch.findings.append(finding)
                claimed.add(i)

    # Second pass: catch-alls get everything left for their rule
    for spec in BATCH_SPECS:
        if not spec.is_catch_all:
            continue
        batch = batches[spec.key]
        for i, finding in enumerate(findings):
            if i in claimed:
                continue
            if finding.rule_id == spec.rule:
                batch.findings.append(finding)
                claimed.add(i)

    return [b for b in batches.values() if b.count > 0]
