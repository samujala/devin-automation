"""Poll GitHub for new auto-remediable issues and match them to DB batches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from orchestrator.store import BatchRow, get_unprocessed_batches

_BASE = "https://api.github.com"
_TIMEOUT = 20.0


@dataclass
class NewWork:
    """A batch that has a GitHub issue and is ready to be sent to Devin."""
    batch: BatchRow
    issue_url: str
    issue_number: int


class GitHubPoller:
    def __init__(self, token: str, repo: str, label: str = "auto-remediable") -> None:
        self._repo = repo
        self._label = label
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _fetch_labeled_issues(self) -> dict[int, dict]:
        """Return {issue_number: issue_data} for open issues with our label."""
        url = f"{_BASE}/repos/{self._repo}/issues"
        params = {"labels": self._label, "state": "open", "per_page": 100}
        issues: dict[int, dict] = {}
        with httpx.Client(timeout=_TIMEOUT) as client:
            while url:
                resp = client.get(url, headers=self._headers, params=params)
                resp.raise_for_status()
                for issue in resp.json():
                    issues[issue["number"]] = issue
                # Handle GitHub pagination
                next_link = resp.links.get("next", {}).get("url")
                url = next_link  # type: ignore[assignment]
                params = {}
        return issues

    def find_new_work(self, db_path: Path) -> list[NewWork]:
        """Return batches that have labeled GitHub issues but aren't yet orchestrated."""
        unprocessed = get_unprocessed_batches(db_path)
        if not unprocessed:
            return []

        labeled_issues = self._fetch_labeled_issues()

        result: list[NewWork] = []
        for batch in unprocessed:
            if batch.github_issue_number not in labeled_issues:
                # Issue was deleted or label was removed — skip silently
                continue
            issue = labeled_issues[batch.github_issue_number]
            result.append(
                NewWork(
                    batch=batch,
                    issue_url=batch.github_issue_url or issue["html_url"],
                    issue_number=batch.github_issue_number,
                )
            )
        return result
