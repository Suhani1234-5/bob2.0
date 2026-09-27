"""
GitHub API client for ProofPR — Phase 3.

Fetches all PR context needed before any agent runs:
  - PR metadata  (title, description, branch, base branch, author, state)
  - Changed files (filename, status, additions, deletions, patch/diff)
  - Full unified diff  (via Accept: application/vnd.github.v3.diff)
  - Linked issues    (parsed from PR body  #NNN  references + GitHub API)

Only outbound dependency: httpx (sync client, no async required here).
Token is read from the GITHUB_TOKEN environment variable.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_API_BASE = "https://api.github.com"
_TOKEN_ENV = "GITHUB_TOKEN"
_DEFAULT_TIMEOUT = 30.0  # seconds


def _token() -> Optional[str]:
    return os.environ.get(_TOKEN_ENV)


def _headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    hdrs = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ProofPR/0.1",
    }
    tok = _token()
    if tok:
        hdrs["Authorization"] = f"Bearer {tok}"
    return hdrs


# ---------------------------------------------------------------------------
# Data classes (plain Python — no Pydantic overhead for internal wiring)
# ---------------------------------------------------------------------------

@dataclass
class ChangedFile:
    filename: str
    status: str            # added | modified | removed | renamed | copied
    additions: int
    deletions: int
    changes: int
    patch: Optional[str] = None   # per-file unified diff hunk (may be absent for binary)


@dataclass
class LinkedIssue:
    number: int
    title: str
    body: Optional[str]
    state: str             # open | closed
    url: str


@dataclass
class PRContext:
    # Core metadata
    repo: str              # "owner/repo"
    pr_number: int
    title: str
    description: Optional[str]
    branch: str            # head ref
    base_branch: str       # base ref
    state: str             # open | closed | merged
    author: str
    created_at: str        # ISO-8601
    updated_at: str
    merged: bool
    merge_commit_sha: Optional[str]
    additions: int
    deletions: int
    changed_files_count: int

    # Rich data
    changed_files: list[ChangedFile] = field(default_factory=list)
    diff: str = ""                          # full unified diff text
    linked_issues: list[LinkedIssue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_repo(repo_url_or_slug: str) -> str:
    """
    Accept any of:
      - "owner/repo"
      - "https://github.com/owner/repo"
      - "https://github.com/owner/repo.git"
      - "git@github.com:owner/repo.git"
    Returns "owner/repo".
    """
    s = repo_url_or_slug.strip().rstrip("/")
    # SSH
    ssh = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", s)
    if ssh:
        return ssh.group(1)
    # HTTPS
    https = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?$", s)
    if https:
        return https.group(1)
    # Already a slug
    if re.match(r"^[^/]+/[^/]+$", s):
        return s
    raise ValueError(f"Cannot parse GitHub repository from: {repo_url_or_slug!r}")


def _issue_numbers_from_body(body: Optional[str]) -> list[int]:
    """
    Extract issue numbers referenced in a PR body.
    Recognises common keywords:
      closes #123  |  fixes #123  |  resolves #123  |  #123  (bare)
    Returns deduplicated, sorted list.
    """
    if not body:
        return []
    pattern = r"""
        (?:
            (?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)   # optional keyword
            \s*:?\s*                                      # optional colon/space
        )?
        \#(\d+)                                           # issue number
    """
    numbers = re.findall(pattern, body, re.IGNORECASE | re.VERBOSE)
    return sorted({int(n) for n in numbers})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_file_contents(
    repo: str,
    ref: str,
    paths: list[str],
) -> dict[str, str]:
    """
    Fetch the text content of one or more files at a given git ref.

    Args:
        repo:  "owner/repo" slug.
        ref:   Branch name, tag, or commit SHA.
        paths: List of relative file paths to fetch.

    Returns:
        Dict mapping path → decoded text content.
        Paths that are binary, too large, or missing are silently omitted.
    """
    result: dict[str, str] = {}
    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        for path in paths:
            resp = client.get(
                f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}",
                headers=_headers(),
                params={"ref": ref},
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            # GitHub returns base64-encoded content for files
            if data.get("encoding") == "base64" and data.get("content"):
                import base64
                try:
                    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                    result[path] = content
                except Exception:
                    pass   # binary or decode error — skip
    return result


class GitHubError(Exception):
    """Raised when the GitHub API returns an unexpected response."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


def fetch_pr_context(repo_url_or_slug: str, pr_number: int) -> PRContext:
    """
    Fetch all PR context from the GitHub REST API.

    Args:
        repo_url_or_slug: Full GitHub URL or "owner/repo" slug.
        pr_number:        The pull request number.

    Returns:
        PRContext populated with metadata, files, diff, and linked issues.

    Raises:
        GitHubError: on any non-2xx GitHub response.
        ValueError:  if the repo string cannot be parsed.
    """
    repo = _parse_repo(repo_url_or_slug)

    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        # ---- 1. PR metadata ------------------------------------------------
        pr_resp = client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}",
            headers=_headers(),
        )
        if pr_resp.status_code != 200:
            raise GitHubError(
                f"GitHub PR fetch failed ({pr_resp.status_code}): {pr_resp.text}",
                pr_resp.status_code,
            )
        pr_data = pr_resp.json()

        # ---- 2. Changed files (paginated, max 300) --------------------------
        changed_files: list[ChangedFile] = []
        page = 1
        while True:
            files_resp = client.get(
                f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/files",
                headers=_headers(),
                params={"per_page": 100, "page": page},
            )
            if files_resp.status_code != 200:
                raise GitHubError(
                    f"GitHub files fetch failed ({files_resp.status_code}): {files_resp.text}",
                    files_resp.status_code,
                )
            batch = files_resp.json()
            if not batch:
                break
            for f in batch:
                changed_files.append(ChangedFile(
                    filename=f["filename"],
                    status=f["status"],
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    changes=f.get("changes", 0),
                    patch=f.get("patch"),        # absent for binary / too-large files
                ))
            if len(batch) < 100:
                break
            page += 1

        # ---- 3. Full unified diff ------------------------------------------
        diff_resp = client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}",
            headers=_headers(accept="application/vnd.github.v3.diff"),
        )
        if diff_resp.status_code != 200:
            raise GitHubError(
                f"GitHub diff fetch failed ({diff_resp.status_code}): {diff_resp.text}",
                diff_resp.status_code,
            )
        full_diff = diff_resp.text

        # ---- 4. Linked issues ----------------------------------------------
        body: Optional[str] = pr_data.get("body")
        issue_numbers = _issue_numbers_from_body(body)
        linked_issues: list[LinkedIssue] = []
        for issue_num in issue_numbers:
            issue_resp = client.get(
                f"{GITHUB_API_BASE}/repos/{repo}/issues/{issue_num}",
                headers=_headers(),
            )
            if issue_resp.status_code == 200:
                iss = issue_resp.json()
                # Skip pull requests that happen to share the same number space
                if "pull_request" not in iss:
                    linked_issues.append(LinkedIssue(
                        number=iss["number"],
                        title=iss["title"],
                        body=iss.get("body"),
                        state=iss["state"],
                        url=iss["html_url"],
                    ))
            # Non-200 for an individual issue is non-fatal; we just skip it.

    # ---- 5. Assemble context -----------------------------------------------
    head = pr_data["head"]
    base = pr_data["base"]

    return PRContext(
        repo=repo,
        pr_number=pr_number,
        title=pr_data["title"],
        description=body,
        branch=head["ref"],
        base_branch=base["ref"],
        state=pr_data["state"],
        author=pr_data["user"]["login"],
        created_at=pr_data["created_at"],
        updated_at=pr_data["updated_at"],
        merged=bool(pr_data.get("merged")),
        merge_commit_sha=pr_data.get("merge_commit_sha"),
        additions=pr_data.get("additions", 0),
        deletions=pr_data.get("deletions", 0),
        changed_files_count=pr_data.get("changed_files", len(changed_files)),
        changed_files=changed_files,
        diff=full_diff,
        linked_issues=linked_issues,
    )
