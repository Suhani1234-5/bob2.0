"""
Compatibility shim and GitHub client for agents and verification routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
import httpx

from app.services.github_service import GitHubService, fetch_file_contents


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ChangedFile:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str | None = None


@dataclass
class LinkedIssue:
    number: int
    title: str
    body: str | None = None
    state: str = "open"
    url: str = ""


@dataclass
class PRContext:
    repo: str
    pr_number: int
    title: str
    description: str | None
    branch: str
    base_branch: str
    state: str
    author: str
    created_at: str
    updated_at: str
    merged: bool
    merge_commit_sha: str | None
    additions: int
    deletions: int
    changed_files_count: int
    changed_files: List[ChangedFile] = field(default_factory=list)
    diff: str = ""
    linked_issues: List[LinkedIssue] = field(default_factory=list)


def fetch_pr_context(repo: str, pr_number: int, token: str | None = None) -> PRContext:
    """Synchronous fetcher required by verification.py and agent modules."""
    gh = GitHubService(token=token)
    repo_name = gh.extract_repo_name(repo)
    headers = gh.headers

    with httpx.Client(timeout=20.0) as client:
        # 1. PR metadata
        pr_resp = client.get(f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}", headers=headers)
        if pr_resp.status_code != 200:
            raise GitHubError(f"GitHub PR fetch failed: {pr_resp.text}", status_code=pr_resp.status_code)
        pr_data = pr_resp.json()

        # 2. Raw diff
        diff_headers = dict(headers)
        diff_headers["Accept"] = "application/vnd.github.v3.diff"
        diff_resp = client.get(f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}", headers=diff_headers)
        diff_text = diff_resp.text if diff_resp.status_code == 200 else ""

        # 3. Changed files
        files_resp = client.get(f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/files", headers=headers)
        raw_files = files_resp.json() if files_resp.status_code == 200 else []

        changed_files = [
            ChangedFile(
                filename=f.get("filename", ""),
                status=f.get("status", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                changes=f.get("changes", 0),
                patch=f.get("patch"),
            )
            for f in raw_files
        ]

        return PRContext(
            repo=repo_name,
            pr_number=pr_number,
            title=pr_data.get("title", ""),
            description=pr_data.get("body"),
            branch=pr_data["head"]["ref"],
            base_branch=pr_data["base"]["ref"],
            state=pr_data.get("state", "open"),
            author=pr_data["user"]["login"] if "user" in pr_data else "unknown",
            created_at=pr_data.get("created_at", ""),
            updated_at=pr_data.get("updated_at", ""),
            merged=pr_data.get("merged", False),
            merge_commit_sha=pr_data.get("merge_commit_sha"),
            additions=pr_data.get("additions", 0),
            deletions=pr_data.get("deletions", 0),
            changed_files_count=len(changed_files),
            changed_files=changed_files,
            diff=diff_text,
            linked_issues=[],
        )