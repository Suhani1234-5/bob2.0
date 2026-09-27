from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agents.fix_verify import FixVerifyError, FixVerifyResult
import routers.fix_verify as fv_router


def _make_result(finding_id: int = 1) -> FixVerifyResult:
    return FixVerifyResult(
        finding_id=finding_id,
        final_status="proven_fixed",
        attempts=1,
        patch_diff="--- a\n+++ b\n",
        patch_summary="Fixed the bug",
        reproduction_passes=True,
        adversarial={"passed": 2, "total": 2, "cases": ["boundary", "null"]},
        regression={"unit": {"passed": 5, "total": 5}, "integration": {"passed": 0, "total": 0},
                    "newly_failing": [], "summary": "Unit 5/5 · no regressions"},
        summary="All checks pass.",
        attempt_log=["Attempt 1 verified"],
    )


_FAKE_EVENTS = [
    {"type": "agent_update",  "agent": "RegressionAgent", "status": "running",
     "message": "Cloning", "pr_id": 1, "finding_id": 1, "timestamp": "2025-01-01T00:00:00Z"},
    {"type": "agent_log",     "agent": "FixerAgent",      "message": "Generating patch",
     "level": "info", "pr_id": 1, "finding_id": 1, "timestamp": "2025-01-01T00:00:01Z"},
    {"type": "finding_status", "status": "proven_fixed",  "message": "All checks pass.",
     "pr_id": 1, "finding_id": 1, "timestamp": "2025-01-01T00:00:02Z"},
]


def _fake_run_fix_verify(finding_id, *, on_event=None, **_kwargs):
    for evt in _FAKE_EVENTS:
        if on_event:
            on_event(evt)
    return _make_result(finding_id)


@pytest.fixture(autouse=True)
def clean_registry():
    fv_router._jobs.clear()
    fv_router._running.clear()
    yield
    fv_router._jobs.clear()
    fv_router._running.clear()


@pytest.fixture
def client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(fv_router.router)
    return TestClient(app, raise_server_exceptions=True)


def _start_and_poll(
    client: TestClient,
    finding_id: int = 1,
    *,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> dict[str, Any]:
    resp = client.post(f"/api/debug/findings/{finding_id}/fix-verify/start")
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status_resp = client.get(f"/api/debug/fix-verify/jobs/{job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(poll_interval)

    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


class TestStartAndPoll:
    def test_returns_202_with_job_metadata(self, client):
        with patch.object(fv_router, "run_fix_verify", side_effect=_fake_run_fix_verify):
            resp = client.post("/api/debug/findings/1/fix-verify/start")

        assert resp.status_code == 202
        body = resp.json()
        assert body["finding_id"] == 1
        assert body["status"] == "running"
        assert "job_id" in body and body["job_id"]

    def test_job_completes_with_correct_result(self, client):
        with patch.object(fv_router, "run_fix_verify", side_effect=_fake_run_fix_verify):
            final = _start_and_poll(client, finding_id=1)

        assert final["status"] == "completed"
        assert final["result"]["final_status"] == "proven_fixed"
        assert final["result"]["finding_id"] == 1
        assert final["result"]["reproduction_passes"] is True
        assert final["error"] is None

    def test_events_are_recorded_in_order(self, client):
        with patch.object(fv_router, "run_fix_verify", side_effect=_fake_run_fix_verify):
            final = _start_and_poll(client, finding_id=1)

        events = final["events"]
        assert len(events) == len(_FAKE_EVENTS)
        for recorded, expected in zip(events, _FAKE_EVENTS):
            assert recorded["type"] == expected["type"]

    def test_events_order_matches_emission_order(self, client):
        with patch.object(fv_router, "run_fix_verify", side_effect=_fake_run_fix_verify):
            final = _start_and_poll(client, finding_id=1)

        types = [e["type"] for e in final["events"]]
        assert types == ["agent_update", "agent_log", "finding_status"]

    def test_start_response_body_fields(self, client):
        with patch.object(fv_router, "run_fix_verify", side_effect=_fake_run_fix_verify):
            resp = client.post("/api/debug/findings/7/fix-verify/start")

        body = resp.json()
        assert set(body.keys()) >= {"job_id", "finding_id", "status"}
        assert body["finding_id"] == 7


class TestDuplicateStart:
    def test_duplicate_start_returns_409(self, client):
        barrier = __import__("threading").Event()

        def _slow_pipeline(finding_id, *, on_event=None, **_kw):
            if on_event:
                on_event(_FAKE_EVENTS[0])
            barrier.wait(timeout=5)
            return _make_result(finding_id)

        with patch.object(fv_router, "run_fix_verify", side_effect=_slow_pipeline):
            resp1 = client.post("/api/debug/findings/1/fix-verify/start")
            assert resp1.status_code == 202

            resp2 = client.post("/api/debug/findings/1/fix-verify/start")
            assert resp2.status_code == 409
            assert "already running" in resp2.json()["detail"].lower()

            barrier.set()


class TestFixVerifyError:
    def test_fix_verify_error_returns_409(self, client):
        def _fail(*_a, **_kw):
            raise FixVerifyError("Finding #99 is 'open'. Only PROVEN findings are fixed.")

        with patch.object(fv_router, "run_fix_verify", side_effect=_fail):
            resp = client.post("/api/debug/findings/99/fix-verify/start")

        assert resp.status_code == 409
        assert "PROVEN" in resp.json()["detail"]

    def test_fix_verify_error_leaves_no_running_entry(self, client):
        def _fail(*_a, **_kw):
            raise FixVerifyError("Finding not found")

        with patch.object(fv_router, "run_fix_verify", side_effect=_fail):
            client.post("/api/debug/findings/5/fix-verify/start")

        assert 5 not in fv_router._running

    def test_fix_verify_error_leaves_no_orphan_job(self, client):
        def _fail(*_a, **_kw):
            raise FixVerifyError("Finding not found")

        with patch.object(fv_router, "run_fix_verify", side_effect=_fail):
            resp = client.post("/api/debug/findings/5/fix-verify/start")
        assert resp.status_code == 409
        assert all(j["finding_id"] != 5 for j in fv_router._jobs.values())


class TestUnknownJob:
    def test_unknown_job_id_returns_404(self, client):
        resp = client.get("/api/debug/fix-verify/jobs/does-not-exist")
        assert resp.status_code == 404

    def test_unknown_job_error_message_is_descriptive(self, client):
        resp = client.get("/api/debug/fix-verify/jobs/no-such-job")
        assert "no-such-job" in resp.json()["detail"]


class TestBlockingEndpoint:
    def test_blocking_endpoint_returns_200_with_result(self, client):
        with patch.object(fv_router, "run_fix_verify", side_effect=_fake_run_fix_verify):
            resp = client.post("/api/debug/findings/1/fix-verify")

        assert resp.status_code == 200
        body = resp.json()
        assert body["final_status"] == "proven_fixed"
        assert body["finding_id"] == 1

    def test_blocking_endpoint_returns_409_on_fix_verify_error(self, client):
        def _fail(*_a, **_kw):
            raise FixVerifyError("Not proven")

        with patch.object(fv_router, "run_fix_verify", side_effect=_fail):
            resp = client.post("/api/debug/findings/1/fix-verify")

        assert resp.status_code == 409
        assert "Not proven" in resp.json()["detail"]
