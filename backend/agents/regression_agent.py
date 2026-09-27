from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


_SUITE_TIMEOUT_SECS: int = int(os.environ.get("REGRESSION_TIMEOUT", "600"))
_AGENT_NAME = "RegressionAgent"

PROOF_DIR = "tests/proof"

_BROKEN_TEST_PATTERNS = (
    r"^\s*ReferenceError:",
    r"^\s*SyntaxError:",
    r"Cannot find module",
    r"is not a constructor",
    r"TS\d{4}:",
)


@dataclass
class TestCaseResult:
    __test__ = False

    test_id:  str
    file:     str
    name:     str
    status:   str
    duration: float
    message:  str = ""


@dataclass
class SuiteRun:
    command:  str
    cases:    list[TestCaseResult] = field(default_factory=list)
    duration: float = 0.0
    exit_code: int | None = None
    output:   str = ""
    error:    str = ""

    @property
    def passed(self) -> int:
        return sum(c.status == "pass" for c in self.cases)

    @property
    def failed(self) -> int:
        return sum(c.status == "fail" for c in self.cases)

    @property
    def errors(self) -> int:
        return sum(c.status == "error" for c in self.cases) + (1 if self.error and not self.cases else 0)

    @property
    def ok(self) -> bool:
        return bool(self.cases) and self.failed == 0 and self.errors == 0

    def failure_lines(self, limit: int = 8) -> list[str]:
        bad = [c for c in self.cases if c.status != "pass"]
        lines = [f"{c.name} [{c.status}]: {c.message[:300]}" for c in bad[:limit]]
        if not self.cases and self.error:
            lines.append(self.error[:600])
        return lines


@dataclass
class RegressionResult:
    baseline:      SuiteRun | None
    patched:       SuiteRun
    newly_failing: list[str]
    unit:          dict[str, int]
    integration:   dict[str, int]
    ok:            bool
    summary:       str


def detect_test_runner(repo_dir: str | Path) -> str:
    pkg = Path(repo_dir) / "package.json"
    text = pkg.read_text(encoding="utf-8").lower() if pkg.exists() else ""
    return "vitest" if "vitest" in text else "jest"


def _npx() -> str:
    return shutil.which("npx") or "npx"


def _build_command(runner: str, report_path: str, files: list[str] | None) -> list[str]:
    if runner == "vitest":
        cmd = [_npx(), "vitest", "run", "--reporter=json", f"--outputFile={report_path}"]
        if files:
            cmd += files
        else:
            cmd += ["--exclude", f"**/{PROOF_DIR}/**"]
        return cmd
    cmd = [_npx(), "jest", "--json", f"--outputFile={report_path}", "--no-coverage", "--forceExit"]
    if files:
        cmd += ["--runTestsByPath", *files]
    else:
        cmd += ["--testPathIgnorePatterns", PROOF_DIR, "/node_modules/"]
    return cmd


def run_tests(
    repo_dir: str | Path,
    runner: str,
    files: list[str] | None = None,
    timeout: int = _SUITE_TIMEOUT_SECS,
) -> SuiteRun:
    repo_dir = Path(repo_dir)
    fd, report_path = tempfile.mkstemp(prefix="proofpr_report_", suffix=".json")
    os.close(fd)
    cmd = _build_command(runner, report_path, files)
    display = " ".join(["npx", *cmd[1:]]).replace(report_path, "<report>.json")

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=repo_dir, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        exit_code, output = proc.returncode, (proc.stdout + proc.stderr)
    except subprocess.TimeoutExpired:
        exit_code, output = None, f"Timed out after {timeout}s"
    except OSError as exc:
        exit_code, output = None, f"Could not start test runner: {exc}"
    elapsed = time.monotonic() - start

    run = SuiteRun(command=display, duration=round(elapsed, 2), exit_code=exit_code, output=output[-4000:])
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        report = {}
    finally:
        Path(report_path).unlink(missing_ok=True)

    if not report:
        run.error = f"Test runner produced no JSON report (exit={exit_code}).\n{output[-1500:]}"
        return run
    run.cases = _parse_report(report, repo_dir)
    if not run.cases:
        run.error = f"No tests were collected.\n{output[-1500:]}"
    return run


def _parse_report(report: dict, repo_dir: Path) -> list[TestCaseResult]:
    cases: list[TestCaseResult] = []
    for suite in report.get("testResults", []):
        rel = _relative(suite.get("name") or suite.get("testFilePath") or "", repo_dir)
        assertions = suite.get("assertionResults") or []
        if not assertions:
            if suite.get("status") == "failed":
                msg = _clean(suite.get("message") or suite.get("failureMessage") or "Test suite failed to run")
                cases.append(TestCaseResult(f"{rel}::<suite>", rel, "<test suite failed to run>", "error", 0.0, msg))
            continue
        for a in assertions:
            name = a.get("fullName") or " ".join([*a.get("ancestorTitles", []), a.get("title", "")]).strip()
            raw_status = a.get("status")
            if raw_status in ("pending", "skipped", "todo", "disabled"):
                continue
            msg = _clean("\n".join(a.get("failureMessages") or []))
            status = "pass" if raw_status == "passed" else "fail"
            if status == "fail" and _is_broken_test(msg):
                status = "error"
            cases.append(
                TestCaseResult(
                    test_id=f"{rel}::{name}",
                    file=rel,
                    name=name,
                    status=status,
                    duration=round((a.get("duration") or 0) / 1000, 3),
                    message=msg,
                )
            )
    return cases


def _relative(path: str, repo_dir: Path) -> str:
    try:
        return Path(path).resolve().relative_to(repo_dir.resolve()).as_posix()
    except (ValueError, OSError):
        return path.replace("\\", "/")


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _clean(text: str) -> str:
    return _ANSI.sub("", text).strip()[:2000]


def _is_broken_test(message: str) -> bool:
    return any(re.search(p, message, re.MULTILINE) for p in _BROKEN_TEST_PATTERNS)


def _category(file: str) -> str:
    lowered = file.lower()
    return "integration" if ("integration" in lowered or "e2e" in lowered) else "unit"


def run_regression_agent(
    repo_dir: str | Path,
    runner: str,
    baseline: SuiteRun | None,
) -> RegressionResult:
    patched = run_tests(repo_dir, runner)

    if baseline is not None and baseline.cases:
        before = {c.test_id: c.status for c in baseline.cases}
        now = {c.test_id: c for c in patched.cases}
        newly_failing = [
            tid for tid, status in before.items()
            if status == "pass" and (tid not in now or now[tid].status != "pass")
        ]
    else:
        newly_failing = [c.test_id for c in patched.cases if c.status != "pass"]

    def tally(cat: str) -> dict[str, int]:
        cs = [c for c in patched.cases if _category(c.file) == cat]
        return {"passed": sum(c.status == "pass" for c in cs), "total": len(cs)}

    unit, integration = tally("unit"), tally("integration")
    ok = bool(patched.cases) and not newly_failing and not (patched.error and not patched.cases)
    pre_existing = sum(1 for c in (baseline.cases if baseline else []) if c.status != "pass")
    summary = (
        f"Unit {unit['passed']}/{unit['total']} · Integration {integration['passed']}/{integration['total']}"
        + (f" · {len(newly_failing)} newly failing" if newly_failing else " · no regressions")
        + (f" · {pre_existing} already failing before the patch" if pre_existing else "")
    )
    logger.info("RegressionAgent: %s", summary)
    return RegressionResult(
        baseline=baseline,
        patched=patched,
        newly_failing=newly_failing,
        unit=unit,
        integration=integration,
        ok=ok,
        summary=summary,
    )
