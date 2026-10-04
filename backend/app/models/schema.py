import enum
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class FindingStatus(str, enum.Enum):
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

class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TestType(str, enum.Enum):
    REPRODUCTION = "reproduction"
    ADVERSARIAL = "adversarial"
    REGRESSION = "regression"
    EDGE_CASE = "edge_case"
    EXISTING = "existing"

class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository: Mapped[str] = mapped_column(String(255), index=True)
    pr_number: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    branch: Mapped[str] = mapped_column(String(255))
    base_branch: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    findings: Mapped[List["Finding"]] = relationship("Finding", back_populates="pr", cascade="all, delete-orphan")
    agent_executions: Mapped[List["AgentExecution"]] = relationship("AgentExecution", back_populates="pr", cascade="all, delete-orphan")

class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity] = mapped_column(SQLEnum(Severity), default=Severity.MEDIUM)
    file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    claim: Mapped[str] = mapped_column(Text)
    status: Mapped[FindingStatus] = mapped_column(SQLEnum(FindingStatus), default=FindingStatus.CANDIDATE, index=True)
    created_by_agent: Mapped[str] = mapped_column(String(100))

    pr: Mapped["PullRequest"] = relationship("PullRequest", back_populates="findings")
    evidences: Mapped[List["Evidence"]] = relationship("Evidence", back_populates="finding", cascade="all, delete-orphan")
    tests: Mapped[List["TestExecution"]] = relationship("TestExecution", back_populates="finding", cascade="all, delete-orphan")
    patch: Mapped[Optional["Patch"]] = relationship("Patch", back_populates="finding", uselist=False, cascade="all, delete-orphan")

class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    finding: Mapped["Finding"] = relationship("Finding", back_populates="evidences")

class TestExecution(Base):
    __tablename__ = "test_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    test_name: Mapped[str] = mapped_column(String(255))
    test_type: Mapped[TestType] = mapped_column(SQLEnum(TestType))
    command: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expected_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    execution_time: Mapped[Optional[float]] = mapped_column(nullable=True)

    finding: Mapped["Finding"] = relationship("Finding", back_populates="tests")

class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), unique=True)
    diff: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(100))
    verification_status: Mapped[str] = mapped_column(String(50), default="pending")

    finding: Mapped["Finding"] = relationship("Finding", back_populates="patch")

class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    finding_id: Mapped[Optional[int]] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    pr_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pr: Mapped[Optional["PullRequest"]] = relationship("PullRequest", back_populates="agent_executions")