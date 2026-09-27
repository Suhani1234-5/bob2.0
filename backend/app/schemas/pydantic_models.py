"""
Pydantic v2 data models for ProofPR entities.
Mirrors the SQLite schema defined in database.py exactly.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class PRStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingStatus(str, Enum):
    CANDIDATE = "candidate"
    INVESTIGATING = "investigating"
    PROVEN = "proven"
    NOT_REPRODUCED = "not_reproduced"
    FIXING = "fixing"
    VERIFYING = "verifying"
    PROVEN_FIXED = "proven_fixed"
    FIX_FAILED = "fix_failed"
    REJECTED = "rejected"
    UNVERIFIED = "unverified"


class EvidenceType(str, Enum):
    CODE = "code"
    TEST_OUTPUT = "test_output"
    AGENT_REASONING = "agent_reasoning"
    REPRODUCTION = "reproduction"
    ADVERSARIAL = "adversarial"
    REGRESSION = "regression"


class TestType(str, Enum):
    REPRODUCTION = "reproduction"
    ADVERSARIAL = "adversarial"
    REGRESSION = "regression"
    EDGE_CASE = "edge_case"
    EXISTING = "existing"


class TestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class PatchVerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Entity models
# ---------------------------------------------------------------------------

class PullRequest(BaseModel):
    id: int
    repository: str
    pr_number: int
    title: str
    description: Optional[str] = None
    branch: str
    base_branch: str
    status: PRStatus = PRStatus.PENDING
    created_at: datetime


class Finding(BaseModel):
    id: int
    pr_id: int
    title: str
    description: Optional[str] = None
    severity: FindingSeverity
    file: Optional[str] = None
    line: Optional[int] = None
    claim: str
    status: FindingStatus = FindingStatus.CANDIDATE
    created_by_agent: str


class Evidence(BaseModel):
    id: int
    finding_id: int
    type: EvidenceType
    description: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    content: Optional[str] = None


class TestExecution(BaseModel):
    id: int
    finding_id: int
    test_name: str
    test_type: TestType
    command: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    status: TestStatus = TestStatus.PENDING
    execution_time: Optional[float] = None   # seconds


class Patch(BaseModel):
    id: int
    finding_id: int
    diff: str
    generated_by: str
    verification_status: PatchVerificationStatus = PatchVerificationStatus.PENDING


class AgentExecution(BaseModel):
    id: int
    agent_name: str
    finding_id: Optional[int] = None
    status: AgentStatus = AgentStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None

class VerifyRequest(BaseModel):
    repo_url: str
    pr_number: int
    issue_url: Optional[str] = None
    custom_requirements: Optional[str] = None

class FindingDetail(Finding):
    evidence: list[Evidence] = []
    tests: list[TestExecution] = []
    patch: Optional[Patch] = None

class PullRequestDetail(PullRequest):
    findings: list[FindingDetail] = []