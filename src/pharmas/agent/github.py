"""GitHub issue lifecycle helpers via the `gh` CLI.

The repo's instruction_for_agent.md and the user's prompt both call for
opening one issue per company at the start of an extraction and updating
it at the end. We keep it simple — `gh` is already in the dev environment.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def detect_repo(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


def gh_available() -> bool:
    try:
        out = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=5)
        return out.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def create_issue(company: str, body: str,
                 cwd: Path | None = None) -> dict[str, str | None]:
    """Open a tracking issue. Returns {url, number, error}.
    Returns {url: None, error: ...} if gh is unavailable or fails."""
    if not gh_available():
        return {"url": None, "number": None, "error": "gh not installed"}
    title = f"[extraction] {company} pipeline"
    try:
        out = subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body],
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
        if out.returncode != 0:
            return {"url": None, "number": None, "error": out.stderr.strip()[:300]}
        m = re.search(r"(https://github\.com/[^/]+/[^/]+/issues/\d+)", out.stdout)
        url = m.group(1) if m else out.stdout.strip().splitlines()[-1]
        number = url.rsplit("/", 1)[-1] if url else None
        return {"url": url, "number": number, "error": None}
    except subprocess.TimeoutExpired:
        return {"url": None, "number": None, "error": "gh issue create timed out"}


def comment_on_issue(issue_url: str, body: str,
                     cwd: Path | None = None) -> str | None:
    if not gh_available() or not issue_url:
        return None
    try:
        out = subprocess.run(
            ["gh", "issue", "comment", issue_url, "--body", body],
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
        return None if out.returncode == 0 else out.stderr.strip()[:300]
    except subprocess.TimeoutExpired:
        return "gh issue comment timed out"


def close_issue(issue_url: str, comment: str | None = None,
                cwd: Path | None = None) -> str | None:
    if not gh_available() or not issue_url:
        return None
    try:
        if comment:
            subprocess.run(
                ["gh", "issue", "comment", issue_url, "--body", comment],
                capture_output=True, text=True, timeout=30, cwd=cwd,
            )
        out = subprocess.run(
            ["gh", "issue", "close", issue_url],
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
        return None if out.returncode == 0 else out.stderr.strip()[:300]
    except subprocess.TimeoutExpired:
        return "gh issue close timed out"