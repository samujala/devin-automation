"""Structured single-line JSON logging for the orchestrator."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def log_event(event: str, **kwargs) -> None:
    record = {"ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"), "event": event}
    record.update(kwargs)
    print(json.dumps(record), flush=True)


def log_error(event: str, exc: BaseException, **kwargs) -> None:
    import traceback
    record = {
        "ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    record.update(kwargs)
    print(json.dumps(record), file=sys.stderr, flush=True)
