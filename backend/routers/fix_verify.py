from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Path as FPath
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from agents.fix_verify import FixVerifyError, FixVerifyResult, run_fix_verify

try:
    from app.services.stream_manager import stream_manager
except ImportError:
    stream_manager = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])


class FixVerifyRequest(BaseModel):
    repro_test_code: str | None = Field(
        None, description="Reproduction test source. Defaults to the finding's 'reproduction' evidence row."
    )
    repro_test_file: str | None = Field(None, examples=["tests/proof/finding-3.proof.test.ts"])
    requirements: list[str] = Field(default_factory=list, description="Acceptance criteria for the fix.")


class FixVerifyResponse(BaseModel):
    finding_id: int
    final_status: str
    attempts: int
    patch_summary: str
    patch_diff: str
    reproduction_passes: bool
    adversarial: dict | None
    regression: dict | None
    summary: str
    attempt_log: list[str]


class JobStartResponse(BaseModel):
    job_id: str
    finding_id: int
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    finding_id: int
    status: str
    events: list[dict[str, Any]]
    result: FixVerifyResponse | None
    error: str | None
    started_at: str
    finished_at: str | None


_jobs: dict[str, dict[str, Any]] = {}
_running: dict[int, str] = {}
_registry_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post("/findings/{finding_id}/fix-verify", response_model=FixVerifyResponse)
async def debug_fix_verify(
    finding_id: int = FPath(..., description="DB id of a PROVEN finding"),
    body: FixVerifyRequest | None = None,
) -> FixVerifyResponse:
    body = body or FixVerifyRequest()
    loop = asyncio.get_running_loop()

    def on_event(event: dict) -> None:
        if stream_manager is not None:
            asyncio.run_coroutine_threadsafe(stream_manager.broadcast(event["pr_id"], event), loop)

    try:
        result = await run_in_threadpool(
            run_fix_verify,
            finding_id,
            repro_test_code=body.repro_test_code,
            repro_test_file=body.repro_test_file,
            requirements=body.requirements,
            on_event=on_event,
        )
    except FixVerifyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return FixVerifyResponse(**result.to_dict())


@router.post(
    "/findings/{finding_id}/fix-verify/start",
    response_model=JobStartResponse,
    status_code=202,
)
async def start_fix_verify(
    finding_id: int = FPath(..., description="DB id of a PROVEN finding"),
    body: FixVerifyRequest | None = None,
) -> JobStartResponse:
    body = body or FixVerifyRequest()

    with _registry_lock:
        if finding_id in _running:
            raise HTTPException(
                status_code=409,
                detail=f"A fix-verify job for finding {finding_id} is already running "
                       f"(job_id={_running[finding_id]}).",
            )
        job_id = str(uuid.uuid4())
        job: dict[str, Any] = {
            "job_id": job_id,
            "finding_id": finding_id,
            "status": "running",
            "events": [],
            "result": None,
            "error": None,
            "started_at": _now_iso(),
            "finished_at": None,
        }
        _jobs[job_id] = job
        _running[finding_id] = job_id

    loop = asyncio.get_running_loop()

    _preflight_done = threading.Event()
    _preflight_error: list[Exception] = []

    def on_event(event: dict) -> None:
        _preflight_done.set()
        with _registry_lock:
            job["events"].append(event)
        if stream_manager is not None:
            asyncio.run_coroutine_threadsafe(stream_manager.broadcast(event["pr_id"], event), loop)

    def _run_pipeline() -> None:
        try:
            result: FixVerifyResult = run_fix_verify(
                finding_id,
                repro_test_code=body.repro_test_code,
                repro_test_file=body.repro_test_file,
                requirements=body.requirements,
                on_event=on_event,
            )
            with _registry_lock:
                job["status"] = "completed"
                job["result"] = FixVerifyResponse(**result.to_dict())
                job["finished_at"] = _now_iso()
        except FixVerifyError as exc:
            _preflight_error.append(exc)
            _preflight_done.set()
            with _registry_lock:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["finished_at"] = _now_iso()
        except Exception as exc:
            _preflight_done.set()
            with _registry_lock:
                job["status"] = "failed"
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["finished_at"] = _now_iso()
            logger.exception("fix-verify background job %s crashed", job_id)
        finally:
            with _registry_lock:
                _running.pop(finding_id, None)

    t = threading.Thread(target=_run_pipeline, daemon=True, name=f"fix-verify-{job_id[:8]}")
    t.start()

    await run_in_threadpool(_preflight_done.wait, 10)

    if _preflight_error:
        with _registry_lock:
            _jobs.pop(job_id, None)
            _running.pop(finding_id, None)
        raise HTTPException(status_code=409, detail=str(_preflight_error[0]))

    return JobStartResponse(job_id=job_id, finding_id=finding_id, status="running")


@router.get("/fix-verify/jobs/{job_id}", response_model=JobStatusResponse)
async def get_fix_verify_job(
    job_id: str = FPath(..., description="Job ID returned by /fix-verify/start"),
) -> JobStatusResponse:
    with _registry_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"No job with id={job_id!r}.")
        snapshot = dict(job)
        snapshot["events"] = list(job["events"])

    return JobStatusResponse(
        job_id=snapshot["job_id"],
        finding_id=snapshot["finding_id"],
        status=snapshot["status"],
        events=snapshot["events"],
        result=snapshot["result"],
        error=snapshot["error"],
        started_at=snapshot["started_at"],
        finished_at=snapshot["finished_at"],
    )
