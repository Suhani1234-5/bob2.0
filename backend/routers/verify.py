"""
POST /api/verify

Accepts { "repo": "<url-or-slug>", "pr_number": <int> }, fetches all PR
context from GitHub, persists a pull_requests row (status = analyzing),
and returns the full fetched context as JSON.

No agents, no findings, no AI — purely GitHub data pull + DB storage.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import get_connection, init_db
from github_client import fetch_pr_context, GitHubError

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    repo: str = Field(..., examples=["https://github.com/owner/repo", "owner/repo"])
    pr_number: int = Field(..., gt=0, examples=[42])


class ChangedFileOut(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str | None = None


class LinkedIssueOut(BaseModel):
    number: int
    title: str
    body: str | None = None
    state: str
    url: str


class VerifyResponse(BaseModel):
    # Stored record
    db_id: int
    db_status: str

    # GitHub metadata
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

    # Rich context
    changed_files: list[ChangedFileOut]
    diff: str
    linked_issues: list[LinkedIssueOut]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/api/verify", response_model=VerifyResponse, status_code=200)
def verify(body: VerifyRequest) -> VerifyResponse:
    """
    1. Fetch PR context from GitHub.
    2. Insert (or update) a pull_requests row with status = 'analyzing'.
    3. Return all fetched data as JSON.
    """
    # -- Fetch from GitHub ---------------------------------------------------
    try:
        ctx = fetch_pr_context(body.repo, body.pr_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GitHubError as exc:
        status_code = exc.status_code or 502
        if status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"PR #{body.pr_number} not found in repository '{body.repo}'.",
            )
        if status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="GitHub authentication failed. Check your GITHUB_TOKEN.",
            )
        raise HTTPException(status_code=502, detail=str(exc))

    # -- Persist to SQLite ---------------------------------------------------
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        # Upsert: if same repo+pr_number already exists, reset status & metadata.
        existing = conn.execute(
            "SELECT id FROM pull_requests WHERE repository = ? AND pr_number = ?",
            (ctx.repo, ctx.pr_number),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE pull_requests
                SET title       = ?,
                    description = ?,
                    branch      = ?,
                    base_branch = ?,
                    status      = 'analyzing'
                WHERE id = ?
                """,
                (ctx.title, ctx.description, ctx.branch, ctx.base_branch, existing["id"]),
            )
            db_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO pull_requests
                    (repository, pr_number, title, description, branch, base_branch, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'analyzing', ?)
                """,
                (ctx.repo, ctx.pr_number, ctx.title, ctx.description,
                 ctx.branch, ctx.base_branch, now),
            )
            db_id = cur.lastrowid

    # -- Build response ------------------------------------------------------
    return VerifyResponse(
        db_id=db_id,
        db_status="analyzing",
        repo=ctx.repo,
        pr_number=ctx.pr_number,
        title=ctx.title,
        description=ctx.description,
        branch=ctx.branch,
        base_branch=ctx.base_branch,
        state=ctx.state,
        author=ctx.author,
        created_at=ctx.created_at,
        updated_at=ctx.updated_at,
        merged=ctx.merged,
        merge_commit_sha=ctx.merge_commit_sha,
        additions=ctx.additions,
        deletions=ctx.deletions,
        changed_files_count=ctx.changed_files_count,
        changed_files=[ChangedFileOut(**asdict(f)) for f in ctx.changed_files],
        diff=ctx.diff,
        linked_issues=[LinkedIssueOut(**asdict(i)) for i in ctx.linked_issues],
    )
