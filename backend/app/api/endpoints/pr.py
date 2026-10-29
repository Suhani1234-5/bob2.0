from fastapi import APIRouter, HTTPException, BackgroundTasks
import app.core.database as db
from app.schemas.pydantic_models import (
    VerifyRequest,
    PullRequest,
    Finding,
    Evidence,
    TestExecution,
    Patch,
    AgentExecution,
    FindingDetail,
)
from app.services.github_service import GitHubService

router = APIRouter()
gh_service = GitHubService()

@router.post("/verify", response_model=PullRequest)
async def start_verification(req: VerifyRequest, background_tasks: BackgroundTasks):
    try:
        repo_name = gh_service.extract_repo_name(req.repo_url)
        gh_pr = await gh_service.get_pull_request(repo_name, req.pr_number)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch PR from GitHub: {str(e)}")

    existing = db.get_pr_by_repo_and_number(repo_name, req.pr_number)
    if existing:
        return PullRequest(**dict(existing), **db.get_pr_test_metrics(existing["id"]))

    pr_id = db.insert_pull_request(
        repository=repo_name,
        pr_number=req.pr_number,
        title=gh_pr.get("title", ""),
        description=gh_pr.get("body", ""),
        branch=gh_pr["head"]["ref"],
        base_branch=gh_pr["base"]["ref"],
        status="analyzing",
        additions=int(gh_pr.get("additions") or 0),
        deletions=int(gh_pr.get("deletions") or 0),
        changed_files_count=int(gh_pr.get("changed_files") or 0),
    )

    created_pr = db.get_pr_by_id(pr_id)
    return PullRequest(**dict(created_pr), **db.get_pr_test_metrics(pr_id))

@router.get("/pr/lookup", response_model=PullRequest)
def get_pr_by_repo_and_number(repository: str, pr_number: int):
    row = db.get_pr_by_repo_and_number(repository, pr_number)
    if not row:
        raise HTTPException(status_code=404, detail="PR not found")
    return PullRequest(**dict(row), **db.get_pr_test_metrics(row["id"]))

@router.get("/pr/{pr_id}", response_model=PullRequest)
def get_pr(pr_id: int):
    row = db.get_pr_by_id(pr_id)
    if not row:
        raise HTTPException(status_code=404, detail="PR not found")
    return PullRequest(**dict(row), **db.get_pr_test_metrics(pr_id))

@router.get("/pr/{pr_id}/findings", response_model=list[Finding])
def get_findings_for_pr(pr_id: int):
    rows = db.get_findings_for_pr(pr_id)
    return [Finding(**dict(r)) for r in rows]

@router.get("/findings/{finding_id}", response_model=FindingDetail)
def get_finding_detail(finding_id: int):
    finding_row = db.get_finding_by_id(finding_id)
    if not finding_row:
        raise HTTPException(status_code=404, detail="Finding not found")

    finding_data = dict(finding_row)
    evidences = [Evidence(**dict(e)) for e in db.get_evidence_for_finding(finding_id)]
    tests = [TestExecution(**dict(t)) for t in db.get_tests_for_finding(finding_id)]
    patch_row = db.get_patch_for_finding(finding_id)
    patch = Patch(**dict(patch_row)) if patch_row else None

    return FindingDetail(**finding_data, evidence=evidences, tests=tests, patch=patch)

@router.get("/findings/{finding_id}/evidence", response_model=list[Evidence])
def get_finding_evidence(finding_id: int):
    return [Evidence(**dict(e)) for e in db.get_evidence_for_finding(finding_id)]

@router.get("/findings/{finding_id}/tests", response_model=list[TestExecution])
def get_finding_tests(finding_id: int):
    return [TestExecution(**dict(t)) for t in db.get_tests_for_finding(finding_id)]

@router.get("/findings/{finding_id}/regression")
def get_finding_regression(finding_id: int):
    if not db.get_finding_by_id(finding_id):
        raise HTTPException(status_code=404, detail="Finding not found")
    return [dict(row) for row in db.get_regression_results_for_finding(finding_id)]

@router.get("/findings/{finding_id}/patch", response_model=Patch)
def get_finding_patch(finding_id: int):
    row = db.get_patch_for_finding(finding_id)
    if not row:
        raise HTTPException(status_code=404, detail="No patch found for finding")
    return Patch(**dict(row))

@router.get("/pr/{pr_id}/timeline", response_model=list[AgentExecution])
def get_timeline(pr_id: int):
    rows = db.get_timeline_for_pr(pr_id)
    return [AgentExecution(**dict(r)) for r in rows]
