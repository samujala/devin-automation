"""Verify is_session_done() handles all expected cases correctly.

Run with:
    python scripts/verify_terminal_check.py
"""

from orchestrator.worker import is_session_done

# Case A: working — should be False
assert is_session_done({"status": "running", "status_enum": "working", "pull_request": None}) is False, "Case A failed"

# Case B: blocked with PR — should be True
assert is_session_done({"status": "running", "status_enum": "blocked", "pull_request": {"url": "https://github.com/x/y/pull/11"}}) is True, "Case B failed"

# Case C: finished without PR — should be True
assert is_session_done({"status": "running", "status_enum": "finished", "pull_request": None}) is True, "Case C failed"

# Case D: stopped — should be True
assert is_session_done({"status": "running", "status_enum": "stopped", "pull_request": None}) is True, "Case D failed"

# Case E: PR opened but status_enum still "working" — should be False (agent still going)
assert is_session_done({"status": "running", "status_enum": "working", "pull_request": {"url": "https://github.com/x/y/pull/11"}}) is False, "Case E failed"

# Case F: PR opened and status_enum is None (unknown) — secondary fallback, should be True
assert is_session_done({"status": "running", "status_enum": None, "pull_request": {"url": "https://github.com/x/y/pull/11"}}) is True, "Case F failed"

# Case G: no PR, status_enum is None — should be False (conservative)
assert is_session_done({"status": "running", "status_enum": None, "pull_request": None}) is False, "Case G failed"

print("OK")
