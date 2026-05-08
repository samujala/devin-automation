"""Thin httpx wrapper for the Devin V1 API.

Verified response shapes (from docs.devin.ai/v1-openapi.yaml):

  POST /v1/sessions
    body:  { "prompt": str, "title": str, ... }
    response: {
        "session_id": str,   # e.g. "devin-abc123"
        "url": str,          # browser link to the session
        "is_new_session": bool
    }

  GET /v1/sessions/{session_id}
    response: {
        "session_id": str,
        "status": str,       # see STATUS_* constants below
        "created_at": str,
        "updated_at": str,
        "pull_request": {"url": str} | null,
        "messages": [...],
        "title": str | null,
        "tags": [...],
        "status_enum": str | null
    }

  DELETE /v1/sessions/{session_id}
    response: {"detail": "Session terminated successfully"} with status 200
    (docs say 204, live API returns 200 with JSON body)

status / status_enum observed live (2026-05-08):
    status is always "running" once started — do NOT use it for terminal detection.
    status_enum is the real signal:
        "working"  — agent actively executing
        "blocked"  — agent finished its task, awaiting human input (OUR terminal state)
        "finished" — session formally closed
        "stopped"  — session terminated
    pull_request.url becomes non-null when Devin opens a PR.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_TIMEOUT = 30.0

@dataclass
class CreatedSession:
    session_id: str
    url: str


@dataclass
class SessionState:
    session_id: str
    status: str
    status_enum: str | None
    pr_url: str | None
    raw: dict


class DevinClient:
    def __init__(self, api_key: str, base_url: str = "https://api.devin.ai/v1") -> None:
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def create_session(self, prompt: str, title: str = "") -> CreatedSession:
        """POST /sessions — start a new Devin session."""
        payload: dict = {"prompt": prompt}
        if title:
            payload["title"] = title
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{self._base}/sessions",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
        data = resp.json()
        return CreatedSession(
            session_id=data["session_id"],
            url=data["url"],
        )

    def get_session(self, session_id: str) -> SessionState:
        """GET /sessions/{session_id} — poll current state."""
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(
                f"{self._base}/sessions/{session_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
        data = resp.json()
        pr = data.get("pull_request")
        pr_url = pr.get("url") if isinstance(pr, dict) else None
        return SessionState(
            session_id=data["session_id"],
            status=data["status"],
            status_enum=data.get("status_enum"),
            pr_url=pr_url,
            raw=data,
        )

    def terminate_session(self, session_id: str) -> None:
        """DELETE /sessions/{session_id} — attempt to stop the session."""
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.delete(
                f"{self._base}/sessions/{session_id}",
                headers=self._headers,
            )
            # 204 or 200 are both fine; surface other errors
            if resp.status_code not in (200, 204):
                resp.raise_for_status()
