"""
Debug / test endpoints — not for production use.

POST /api/debug/requirement-agent
    Fetch PR from GitHub + run Requirement Agent (Phase 4).

GET /api/debug/pr/{pr_id}/investigate
    Given a DB pr_id (from POST /api/verify), re-fetch PR context from
    GitHub, run Requirement Agent then Investigator Agent, store candidate
    findings in the DB, and return them.  Clears any existing findings for
    the PR first so the endpoint is safely re-runnable.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Path as FPath
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from agents.investigator_agent import (
    CandidateFinding,
    InvestigatorAgentError,
    run_investigator_agent,
)
from agents.reproducer_agent import (
    ReproducerAgentError,
    ReproductionResult,
    run_reproducer_agent,
)
from agents.requirement_agent import (
    RequirementAgentError,
    RequirementResult,
    run_requirement_agent,
)
from database import (
    get_connection,
    get_finding_by_id,
    get_findings_for_pr,
    get_pr_by_id,
    insert_findings,
    insert_test_execution,
    update_finding_status,
)
from github_client import GitHubError, fetch_file_contents, fetch_pr_context

router = APIRouter(prefix="/api/debug", tags=["debug"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RequirementAgentRequest(BaseModel):
    repo: str = Field(..., examples=["owner/repo", "https://github.com/owner/repo"])
    pr_number: int = Field(..., gt=0, examples=[42])


class PRContextSummary(BaseModel):
    repo: str
    pr_number: int
    title: str
    description: str | None
    branch: str
    base_branch: str
    author: str
    state: str
    changed_files_count: int
    additions: int
    deletions: int
    linked_issue_numbers: list[int]
    diff_length_chars: int


class RequirementAgentResponse(BaseModel):
    pr_context_summary: PRContextSummary
    requirement_result: dict          # RequirementResult.to_dict()
    raw_model: str | None = None      # model name used (for tracing)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/requirement-agent", response_model=RequirementAgentResponse)
def debug_requirement_agent(body: RequirementAgentRequest) -> RequirementAgentResponse:
    """
    Fetch PR context from GitHub, run the Requirement Agent, return both.
    Useful for verifying the agent output against a real PR before wiring
    it into the full verification pipeline.
    """
    # -- Step 1: fetch PR context --------------------------------------------
    try:
        ctx = fetch_pr_context(body.repo, body.pr_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GitHubError as exc:
        code = exc.status_code or 502
        if code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"PR #{body.pr_number} not found in '{body.repo}'.",
            )
        if code == 401:
            raise HTTPException(
                status_code=401,
                detail="GitHub authentication failed. Check GITHUB_TOKEN.",
            )
        raise HTTPException(status_code=502, detail=str(exc))

    # -- Step 2: run requirement agent ---------------------------------------
    try:
        result: RequirementResult = run_requirement_agent(ctx)
    except RequirementAgentError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": str(exc),
                "raw_response": exc.raw_response[:1000] if exc.raw_response else None,
            },
        )

    # -- Step 3: build response ----------------------------------------------
    summary = PRContextSummary(
        repo=ctx.repo,
        pr_number=ctx.pr_number,
        title=ctx.title,
        description=ctx.description,
        branch=ctx.branch,
        base_branch=ctx.base_branch,
        author=ctx.author,
        state=ctx.state,
        changed_files_count=ctx.changed_files_count,
        additions=ctx.additions,
        deletions=ctx.deletions,
        linked_issue_numbers=[i.number for i in ctx.linked_issues],
        diff_length_chars=len(ctx.diff),
    )

    model_used = os.environ.get("BOB_MODEL", "gpt-4o")

    return RequirementAgentResponse(
        pr_context_summary=summary,
        requirement_result=result.to_dict(),
        raw_model=model_used,
    )


# ---------------------------------------------------------------------------
# Investigator debug endpoint — GET /api/debug/pr/{pr_id}/investigate
# ---------------------------------------------------------------------------

class FindingOut(BaseModel):
    id: int
    pr_id: int
    title: str
    description: str | None
    severity: str
    file: str | None
    line: int | None
    claim: str
    status: str
    created_by_agent: str


class InvestigateResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    pr_id: int
    repo: str
    pr_number: int
    requirement: str
    findings_stored: int
    findings: list[FindingOut]
    model_used: str


@router.get("/pr/{pr_id}/investigate", response_model=InvestigateResponse)
def debug_investigate(
    pr_id: int = FPath(..., description="DB id from pull_requests table"),
) -> InvestigateResponse:
    """
    Trigger the full context → investigator pipeline for a stored PR.

    Steps:
      1. Load the PR record from DB (must already exist via POST /api/verify).
      2. Re-fetch fresh PR context from GitHub.
      3. Run Requirement Agent → RequirementResult.
      4. Run Investigator Agent → list[CandidateFinding].
      5. Delete any previously stored findings for this PR (idempotent re-runs).
      6. Insert new candidate findings linked to pr_id.
      7. Return the stored findings.
    """
    # -- Step 1: load PR from DB ---------------------------------------------
    pr_row = get_pr_by_id(pr_id)
    if pr_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PR found with id={pr_id}. Run POST /api/verify first.",
        )

    repo       = pr_row["repository"]
    pr_number  = pr_row["pr_number"]

    # -- Step 2: re-fetch PR context from GitHub -----------------------------
    try:
        ctx = fetch_pr_context(repo, pr_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GitHubError as exc:
        code = exc.status_code or 502
        if code == 404:
            raise HTTPException(status_code=404, detail=f"PR not found on GitHub: {exc}")
        if code == 401:
            raise HTTPException(status_code=401, detail="GitHub auth failed. Check GITHUB_TOKEN.")
        raise HTTPException(status_code=502, detail=str(exc))

    # -- Step 3: run Requirement Agent ---------------------------------------
    try:
        req_result: RequirementResult = run_requirement_agent(ctx)
    except RequirementAgentError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": str(exc), "raw_response": exc.raw_response[:1000] if exc.raw_response else None},
        )

    # -- Step 4: run Investigator Agent --------------------------------------
    try:
        candidates: list[CandidateFinding] = run_investigator_agent(ctx, req_result)
    except InvestigatorAgentError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": str(exc), "raw_response": exc.raw_response[:1000] if exc.raw_response else None},
        )

    # -- Step 5: clear old findings for this PR (idempotent re-runs) ---------
    with get_connection() as conn:
        conn.execute("DELETE FROM findings WHERE pr_id = ?", (pr_id,))

    # -- Step 6: insert new candidate findings -------------------------------
    insert_findings(pr_id, candidates)

    # -- Step 7: read back from DB and return --------------------------------
    rows = get_findings_for_pr(pr_id)
    findings_out = [
        FindingOut(
            id=row["id"],
            pr_id=row["pr_id"],
            title=row["title"],
            description=row["description"],
            severity=row["severity"],
            file=row["file"],
            line=row["line"],
            claim=row["claim"],
            status=row["status"],
            created_by_agent=row["created_by_agent"],
        )
        for row in rows
    ]

    return InvestigateResponse(
        pr_id=pr_id,
        repo=repo,
        pr_number=pr_number,
        requirement=req_result.requirement,
        findings_stored=len(findings_out),
        findings=findings_out,
        model_used=os.environ.get("BOB_MODEL", "gpt-4o"),
    )


# ---------------------------------------------------------------------------
# Reproducer debug endpoint — GET /api/debug/findings/{finding_id}/reproduce
# ---------------------------------------------------------------------------

class ReproduceResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    finding_id:     int
    finding_title:  str
    finding_status: str        # updated value now stored in DB
    test_file_path: str
    test_status:    str        # pass | fail | error
    exit_code:      int | None
    execution_time: float
    expected_result: str
    actual_result:  str
    stdout:         str
    stderr:         str
    model_used:     str
    # The generated test source, for inspection
    test_code:      str


@router.get("/findings/{finding_id}/reproduce", response_model=ReproduceResponse)
def debug_reproduce(
    finding_id: int = FPath(..., description="DB id from findings table"),
) -> ReproduceResponse:
    """
    Trigger the Reproducer Agent for a single finding.

    Steps:
      1. Load the finding row (must exist — run /investigate first).
      2. Load its parent PR row to get repo + branch.
      3. Fetch relevant source files from GitHub (the file named in the finding,
         plus package.json).
      4. Run the Reproducer Agent: generate test → clone → install → execute.
      5. Update finding.status in DB.
      6. Insert a test_executions row.
      7. Return full result.
    """
    # 1. Load finding
    finding_row = get_finding_by_id(finding_id)
    if finding_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No finding with id={finding_id}. Run /investigate first.",
        )

    # 2. Load parent PR
    pr_row = get_pr_by_id(finding_row["pr_id"])
    if pr_row is None:
        raise HTTPException(status_code=404, detail="Parent PR record not found.")

    repo   = pr_row["repository"]
    branch = pr_row["branch"]

    # 3. Fetch source files from GitHub
    paths_to_fetch: list[str] = ["package.json"]
    if finding_row["file"]:
        paths_to_fetch.append(finding_row["file"])

    try:
        source_map = fetch_file_contents(repo, branch, paths_to_fetch)
    except Exception as exc:
        # Non-fatal — proceed without source; the agent will do its best
        logger.warning("debug_reproduce: could not fetch source files: %s", exc)
        source_map = {}

    package_json = source_map.pop("package.json", None)
    # Remaining entries are source files for the finding
    source_files = source_map

    # 4. Run Reproducer Agent
    try:
        result: ReproductionResult = run_reproducer_agent(
            finding_id=finding_id,
            title=finding_row["title"],
            claim=finding_row["claim"],
            description=finding_row["description"] or "",
            file=finding_row["file"],
            line=finding_row["line"],
            repo=repo,
            branch=branch,
            source_files=source_files,
            package_json=package_json,
        )
    except ReproducerAgentError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": str(exc),
                "raw_response": exc.raw_response[:1000] if exc.raw_response else None,
            },
        )

    # 5. Update finding status in DB
    # Map reproducer outcome → PRD state machine
    # proven            → PROVEN  (test confirmed the bug)
    # not_reproduced    → REJECTED (evidence contradicts the claim)
    # unverified        → UNVERIFIED (inconclusive)
    db_status_map = {
        "proven":           "proven",
        "not_reproduced":   "rejected",
        "unverified":       "unverified",
    }
    new_db_status = db_status_map.get(result.finding_status, "unverified")
    update_finding_status(finding_id, new_db_status)

    # 6. Insert test execution row
    insert_test_execution(
        finding_id=finding_id,
        test_name=result.test_file_path or f"finding-{finding_id}.proof.test.ts",
        test_type="reproduction",
        command=result.command,
        expected_result=result.expected_result,
        actual_result=result.actual_result,
        status=result.test_status,
        execution_time=result.execution_time,
    )

    # 7. Return
    return ReproduceResponse(
        finding_id=finding_id,
        finding_title=finding_row["title"],
        finding_status=new_db_status,
        test_file_path=result.test_file_path,
        test_status=result.test_status,
        exit_code=result.exit_code,
        execution_time=round(result.execution_time, 2),
        expected_result=result.expected_result,
        actual_result=result.actual_result,
        stdout=result.stdout[:4000],
        stderr=result.stderr[:4000],
        model_used=os.environ.get("BOB_MODEL", "gpt-4o"),
        test_code=result.test_code,
    )
