"""Thin httpx wrapper for GitHub Issues REST API."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


_BASE = "https://api.github.com"
_TIMEOUT = 20.0


@dataclass
class CreatedIssue:
    number: int
    url: str


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        """
        Args:
            token: Fine-grained PAT with Issues: Read + Write.
            repo:  ``owner/repo`` string, e.g. ``samujala/superset``.
        """
        self._repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def ensure_label(self, label: str, color: str = "0075ca") -> None:
        """Create *label* on the repo if it doesn't already exist."""
        url = f"{_BASE}/repos/{self._repo}/labels"
        with httpx.Client(timeout=_TIMEOUT) as client:
            # Check if label exists
            resp = client.get(f"{url}/{label}", headers=self._headers)
            if resp.status_code == 200:
                return
            if resp.status_code != 404:
                resp.raise_for_status()
            # Create it
            resp = client.post(
                url,
                headers=self._headers,
                json={"name": label, "color": color},
            )
            resp.raise_for_status()

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> CreatedIssue:
        """Open a new issue and return its number + URL."""
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        url = f"{_BASE}/repos/{self._repo}/issues"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()

        data = resp.json()
        return CreatedIssue(number=data["number"], url=data["html_url"])
