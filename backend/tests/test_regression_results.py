from types import SimpleNamespace
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.endpoints.pr as pr_endpoint
import app.core.database as db


def test_regression_results_persist_and_upsert(tmp_path):
    db_path = tmp_path / "regression.db"
    db.init_db(db_path)
    pr_id = db.insert_pull_request("owner/repo", 1, "PR", None, "feature", "main", db_path=db_path)
    finding_id = db.insert_findings(
        pr_id,
        [SimpleNamespace(title="Bug", description=None, severity="high", file=None, line=None, claim="claim", reason="The defect was confirmed.")],
        db_path=db_path,
    )[0]
    assert db.get_finding_by_id(finding_id, db_path)["reason"] == "The defect was confirmed."
    db.update_finding_status(finding_id, "proven_fixed", db_path=db_path, reason="The fix passed regression checks.")
    assert db.get_finding_by_id(finding_id, db_path)["reason"] == "The fix passed regression checks."

    db.insert_regression_result(finding_id, "integration", 13, 13, db_path)
    db.insert_regression_result(finding_id, "unit", 34, 34, db_path)
    db.insert_regression_result(finding_id, "proof", 7, 7, db_path)
    db.insert_regression_result(finding_id, "unit", 33, 34, db_path)

    rows = db.get_regression_results_for_finding(finding_id, db_path)
    assert [(row["suite"], row["passed"], row["total"]) for row in rows] == [
        ("unit", 33, 34),
        ("integration", 13, 13),
        ("proof", 7, 7),
    ]


def test_init_db_migrates_existing_findings_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy_schema = db._SCHEMA_SQL.replace(
        "    created_by_agent  TEXT    NOT NULL,\n    reason            TEXT",
        "    created_by_agent  TEXT    NOT NULL",
    )
    with sqlite3.connect(db_path) as connection:
        connection.executescript(legacy_schema)

    db.init_db(db_path)

    with db.get_connection(db_path) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(findings)")}
    assert "reason" in columns


def test_pr_test_metrics_deduplicates_regression_and_proof_rows(tmp_path):
    db_path = tmp_path / "pr-metrics.db"
    db.init_db(db_path)
    pr_id = db.insert_pull_request(
        "shop-api", 42, "Coupon validation", None, "feature", "main",
        db_path=db_path, additions=143, deletions=27, changed_files_count=6,
    )
    finding_id = db.insert_findings(
        pr_id,
        [SimpleNamespace(title="Bug", description=None, severity="high", file=None, line=None, claim="claim")],
        db_path=db_path,
    )[0]
    db.insert_test_execution(finding_id, "repro", "reproduction", "test", "fails", "failed", "pass", 0.1, db_path)
    db.insert_test_execution(finding_id, "proof copy", "proof", "test", "passes", "passes", "pass", 0.1, db_path)
    db.insert_test_execution(finding_id, "adversarial", "adversarial", "test", "passes", "passes", "pass", 0.1, db_path)
    db.insert_test_execution(finding_id, "unit summary", "regression", "test", "all pass", "aggregate", "fail", 0.1, db_path)
    for suite, passed, total in (("unit", 34, 34), ("integration", 13, 13), ("proof", 7, 7)):
        db.insert_regression_result(finding_id, suite, passed, total, db_path)

    pr = db.get_pr_by_id(pr_id, db_path)
    metrics = db.get_pr_test_metrics(pr_id, db_path)
    assert (pr["additions"], pr["deletions"], pr["changed_files_count"]) == (143, 27, 6)
    assert metrics == {"tests_passed": 55, "tests_total": 55, "confidence": 100.0}


def test_pr_endpoint_returns_change_and_test_metrics(monkeypatch):
    pr = {
        "id": 4,
        "repository": "shop-api",
        "pr_number": 42,
        "title": "Coupon validation",
        "description": None,
        "branch": "feature",
        "base_branch": "main",
        "status": "completed",
        "additions": 143,
        "deletions": 27,
        "changed_files_count": 6,
        "created_at": "2026-10-23T00:00:00Z",
    }
    monkeypatch.setattr(pr_endpoint.db, "get_pr_by_id", lambda pr_id: pr if pr_id == 4 else None)
    monkeypatch.setattr(
        pr_endpoint.db,
        "get_pr_by_repo_and_number",
        lambda repository, pr_number: pr if (repository, pr_number) == ("shop-api", 42) else None,
    )
    monkeypatch.setattr(
        pr_endpoint.db,
        "get_pr_test_metrics",
        lambda _pr_id: {"tests_passed": 55, "tests_total": 55, "confidence": 100.0},
    )
    app = FastAPI()
    app.include_router(pr_endpoint.router, prefix="/api")

    response = TestClient(app).get("/api/pr/4")

    assert response.status_code == 200
    assert response.json()["additions"] == 143
    assert response.json()["changed_files_count"] == 6
    assert response.json()["tests_passed"] == 55
    assert response.json()["tests_total"] == 55
    assert response.json()["confidence"] == 100.0

    lookup = TestClient(app).get("/api/pr/lookup?repository=shop-api&pr_number=42")
    assert lookup.status_code == 200
    assert lookup.json()["tests_passed"] == 55


def test_regression_endpoint_returns_rows_or_404(monkeypatch):
    rows = [
        {"id": 1, "finding_id": 7, "suite": "unit", "passed": 34, "total": 34},
        {"id": 2, "finding_id": 7, "suite": "integration", "passed": 13, "total": 13},
    ]
    monkeypatch.setattr(pr_endpoint.db, "get_finding_by_id", lambda finding_id: {"id": finding_id} if finding_id == 7 else None)
    monkeypatch.setattr(pr_endpoint.db, "get_regression_results_for_finding", lambda finding_id: rows)

    app = FastAPI()
    app.include_router(pr_endpoint.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/findings/7/regression")
    assert response.status_code == 200
    assert [(row["suite"], row["passed"], row["total"]) for row in response.json()] == [
        ("unit", 34, 34),
        ("integration", 13, 13),
    ]
    assert client.get("/api/findings/99/regression").status_code == 404


def test_finding_detail_endpoint_returns_reason(monkeypatch):
    finding = {
        "id": 7,
        "pr_id": 3,
        "title": "Missing auth guard",
        "description": None,
        "severity": "high",
        "file": None,
        "line": None,
        "claim": "A user may be missing.",
        "status": "rejected",
        "created_by_agent": "investigator",
        "reason": "Rejected: auth middleware already guarantees a non-null user.",
    }
    monkeypatch.setattr(pr_endpoint.db, "get_finding_by_id", lambda finding_id: finding if finding_id == 7 else None)
    monkeypatch.setattr(pr_endpoint.db, "get_evidence_for_finding", lambda _finding_id: [])
    monkeypatch.setattr(pr_endpoint.db, "get_tests_for_finding", lambda _finding_id: [])
    monkeypatch.setattr(pr_endpoint.db, "get_patch_for_finding", lambda _finding_id: None)

    app = FastAPI()
    app.include_router(pr_endpoint.router, prefix="/api")
    response = TestClient(app).get("/api/findings/7")

    assert response.status_code == 200
    assert response.json()["reason"] == finding["reason"]
