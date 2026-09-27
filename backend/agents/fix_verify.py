from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import database as db
from agents.adversarial_agent import (
    AdversarialAgentError,
    AdversarialSuite,
    repair_adversarial_suite,
    run_adversarial_agent,
)
from agents.fixer_agent import (
    FixerAgentError,
    FixProposal,
    PatchApplyError,
    apply_edits,
    run_fixer_agent,
)
from agents.regression_agent import (
    PROOF_DIR,
    RegressionResult,
    SuiteRun,
    _category,
    detect_test_runner,
    run_regression_agent,
    run_tests,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = int(os.environ.get("FIXER_MAX_ATTEMPTS", "2"))
_INSTALL_TIMEOUT = int(os.environ.get("FIX_VERIFY_INSTALL_TIMEOUT", "600"))
_MAX_SOURCE_FILES = 4

FIXER, ADVERSARIAL, REGRESSION = "FixerAgent", "AdversarialVerifier", "RegressionAgent"

EventCallback = Callable[[dict], None]


@dataclass
class FixVerifyResult:
    finding_id: int
    final_status: str
    attempts: int
    patch_diff: str
    patch_summary: str
    reproduction_passes: bool
    adversarial: dict | None
    regression: dict | None
    summary: str
    attempt_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class FixVerifyError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Reporter:
    def __init__(self, pr_id: int, finding_id: int, db_path: Path, on_event: Optional[EventCallback]):
        self.pr_id, self.finding_id, self.db_path, self.on_event = pr_id, finding_id, db_path, on_event
        self.rows: dict[str, int] = {}

    def _emit(self, payload: dict) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event({"pr_id": self.pr_id, "finding_id": self.finding_id, "timestamp": _now(), **payload})
        except Exception:
            logger.exception("fix_verify: on_event callback failed")

    def log(self, agent: str, message: str, level: str = "info") -> None:
        logger.info("[%s] finding #%s: %s", agent, self.finding_id, message)
        self._emit({"type": "agent_log", "agent": agent, "message": message, "level": level})

    def start(self, agent: str, message: str) -> None:
        with db.get_connection(self.db_path) as conn:
            if agent in self.rows:
                conn.execute(
                    "UPDATE agent_executions SET status='running', completed_at=NULL, summary=? WHERE id=?",
                    (message, self.rows[agent]),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO agent_executions (agent_name, finding_id, status, started_at, summary) "
                    "VALUES (?, ?, 'running', ?, ?)",
                    (agent, self.finding_id, _now(), message),
                )
                self.rows[agent] = cur.lastrowid
        self._emit({"type": "agent_update", "agent": agent, "status": "running", "message": message})

    def finish(self, agent: str, message: str, ok: bool = True) -> None:
        status = "completed" if ok else "failed"
        if agent in self.rows:
            with db.get_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE agent_executions SET status=?, completed_at=?, summary=? WHERE id=?",
                    (status, _now(), message, self.rows[agent]),
                )
        self._emit({"type": "agent_update", "agent": agent, "status": status, "message": message})

    def status(self, status: str, message: str) -> None:
        db.update_finding_status(self.finding_id, status, db_path=self.db_path)
        self._emit({"type": "finding_status", "status": status, "message": message})


def _find_reproduction(finding_id: int, db_path: Path) -> tuple[str, str] | None:
    with db.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT file, content FROM evidence WHERE finding_id = ? AND type = 'reproduction' "
            "AND content IS NOT NULL AND content != '' ORDER BY id DESC LIMIT 1",
            (finding_id,),
        ).fetchone()
    if row is None:
        return None
    return row["file"] or f"{PROOF_DIR}/finding-{finding_id}.proof.test.ts", row["content"]


def _rmtree(path: str) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def _git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )


def _clone(repo: str, branch: str, dest: Path) -> None:
    if Path(repo).is_dir():
        proc = subprocess.run(
            ["git", "clone", "-q", "--branch", branch, str(Path(repo).resolve()), str(dest)],
            capture_output=True, text=True, timeout=300,
        )
    else:
        from agents.reproducer_agent import _clone_and_checkout
        proc = _clone_and_checkout(repo, branch, str(dest))
    if proc.returncode != 0:
        raise FixVerifyError(f"git clone of {repo}@{branch} failed: {proc.stderr[-800:]}")


def _install(repo_dir: Path) -> None:
    npm = shutil.which("npm") or "npm"
    for cmd in ([npm, "ci", "--prefer-offline", "--no-audit", "--no-fund"], [npm, "install", "--no-audit", "--no-fund"]):
        proc = subprocess.run(
            cmd, cwd=repo_dir, capture_output=True, text=True, timeout=_INSTALL_TIMEOUT,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0:
            return
    raise FixVerifyError(f"npm install failed: {proc.stderr[-800:]}")


_IMPORT_RE = re.compile(r"""(?:import|from)\s*[^'"]*['"](\.{1,2}/[^'"]+)['"]|require\(\s*['"](\.{1,2}/[^'"]+)['"]\s*\)""")


def _local_imports(repo_dir: Path, rel_file: str) -> list[str]:
    path = repo_dir / rel_file
    if not path.is_file():
        return []
    found = []
    for m in _IMPORT_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
        target = (path.parent / (m.group(1) or m.group(2))).resolve()
        for cand in (target, *(target.with_name(target.name + ext) for ext in (".ts", ".tsx", ".js", ".mjs")),
                     target / "index.ts", target / "index.js"):
            if cand.is_file():
                try:
                    found.append(cand.relative_to(repo_dir.resolve()).as_posix())
                except ValueError:
                    pass
                break
    return found


def _source_files(repo_dir: Path, finding_file: Optional[str], repro_file: str) -> dict[str, str]:
    ordered: list[str] = []
    if finding_file:
        ordered.append(finding_file.lstrip("./").replace("\\", "/"))
    ordered += _local_imports(repo_dir, repro_file)
    if finding_file:
        ordered += _local_imports(repo_dir, ordered[0])
    out: dict[str, str] = {}
    for rel in ordered:
        if rel in out or rel.startswith("tests/") or ".test." in rel or ".spec." in rel:
            continue
        p = repo_dir / rel
        if p.is_file():
            out[rel] = p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        if len(out) >= _MAX_SOURCE_FILES:
            break
    return out


def _failure_text(run: SuiteRun) -> str:
    lines = run.failure_lines()
    return "\n".join(lines) if lines else run.output[-1200:]


def _save_patch(finding_id: int, diff: str, status: str, db_path: Path) -> None:
    with db.get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM patches WHERE finding_id = ? ORDER BY id LIMIT 1", (finding_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE patches SET diff = ?, generated_by = ?, verification_status = ? WHERE id = ?",
                (diff, FIXER, status, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO patches (finding_id, diff, generated_by, verification_status) VALUES (?, ?, ?, ?)",
                (finding_id, diff, FIXER, status),
            )


def _save_evidence(finding_id: int, etype: str, description: str, content: str, db_path: Path,
                   file: str | None = None) -> None:
    with db.get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO evidence (finding_id, type, description, file, line, content) VALUES (?, ?, ?, ?, NULL, ?)",
            (finding_id, etype, description, file, content),
        )


def _save_tests(finding_id: int, db_path: Path, repro: SuiteRun | None, repro_file: str,
                adversarial: SuiteRun | None, adversarial_cases: list[str],
                regression: RegressionResult | None) -> None:
    def insert(name, ttype, command, expected, actual, status, seconds):
        db.insert_test_execution(
            finding_id=finding_id, test_name=name, test_type=ttype, command=command,
            expected_result=expected, actual_result=actual, status=status,
            execution_time=seconds, db_path=db_path,
        )

    if repro is not None:
        for c in repro.cases:
            insert(f"{repro_file} (after fix)", "reproduction", repro.command,
                   "Passes once the defect is fixed", c.message or "Passed", c.status, c.duration)
    if adversarial is not None:
        labels = {i: l for i, l in enumerate(adversarial_cases)}
        for i, c in enumerate(adversarial.cases):
            insert(labels.get(i) or c.name, "adversarial", adversarial.command,
                   "Behaviour required by the finding holds", c.message or "Passed", c.status, c.duration)
    if regression is not None:
        p = regression.patched
        broken = {_category(tid.split("::")[0]) for tid in regression.newly_failing}
        for cat in ("unit", "integration"):
            t = getattr(regression, cat)
            if t["total"]:
                insert(f"Existing {cat} tests", "regression", p.command, "No test that passed before the patch fails",
                       f"{t['passed']}/{t['total']} passed", "fail" if cat in broken else "pass", p.duration)
        for tid in regression.newly_failing[:20]:
            case = next((c for c in p.cases if c.test_id == tid), None)
            insert(tid, "regression", p.command, "Passed before the patch",
                   (case.message if case else "Missing after patch") or "Failed", "fail",
                   case.duration if case else None)


def run_fix_verify(
    finding_id: int,
    *,
    repro_test_code: Optional[str] = None,
    repro_test_file: Optional[str] = None,
    requirements: Optional[list[str]] = None,
    on_event: Optional[EventCallback] = None,
    db_path: Optional[Path] = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> FixVerifyResult:
    db_path = Path(db_path or os.environ.get("PROOFPR_DB_PATH") or db.DB_PATH)
    finding = db.get_finding_by_id(finding_id, db_path=db_path)
    if finding is None:
        raise FixVerifyError(f"No finding with id={finding_id}.")
    if finding["status"] not in ("proven", "fix_failed"):
        raise FixVerifyError(
            f"Finding #{finding_id} is '{finding['status']}'. Only PROVEN findings are fixed "
            "(run the Reproducer first)."
        )
    pr = db.get_pr_by_id(finding["pr_id"], db_path=db_path)
    if pr is None:
        raise FixVerifyError("Parent PR record not found.")

    if not repro_test_code:
        stored = _find_reproduction(finding_id, db_path)
        if stored is None:
            raise FixVerifyError(
                "No reproduction test available. Pass repro_test_code, or store it as an evidence row "
                "(type='reproduction', file=<test path>, content=<test code>)."
            )
        repro_test_file, repro_test_code = repro_test_file or stored[0], stored[1]
    repro_test_file = (repro_test_file or f"finding-{finding_id}.proof.test.ts").replace("\\", "/")
    if "/" not in repro_test_file:
        repro_test_file = f"{PROOF_DIR}/{repro_test_file}"
    adversarial_file = f"{PROOF_DIR}/finding-{finding_id}.adversarial.test.ts"

    rep = _Reporter(finding["pr_id"], finding_id, db_path, on_event)
    reqs = list(requirements or [])
    if not reqs and pr["description"]:
        reqs = [pr["description"].strip()[:600]]

    tmpdir = tempfile.mkdtemp(prefix="proofpr_fix_")
    ws = Path(tmpdir) / "repo"
    try:
        rep.start(REGRESSION, "Preparing sandbox: cloning PR branch and installing dependencies")
        try:
            _clone(pr["repository"], pr["branch"], ws)
            _install(ws)
        except (FixVerifyError, subprocess.TimeoutExpired, OSError) as exc:
            rep.finish(REGRESSION, f"Sandbox setup failed: {exc}", ok=False)
            raise FixVerifyError(str(exc)) from exc
        runner = detect_test_runner(ws)
        (ws / repro_test_file).parent.mkdir(parents=True, exist_ok=True)
        (ws / repro_test_file).write_text(repro_test_code, encoding="utf-8")

        rep.log(REGRESSION, f"Running existing {runner} suite on the unpatched PR branch (baseline)")
        baseline = run_tests(ws, runner)
        rep.finish(REGRESSION, f"Baseline: {baseline.passed}/{len(baseline.cases)} existing tests pass")

        before = run_tests(ws, runner, [repro_test_file])
        if before.failed == 0:
            why = ("the reproduction test passes on the PR branch" if before.ok
                   else "the reproduction test does not run: " + _failure_text(before)[:300])
            raise FixVerifyError(f"Cannot fix finding #{finding_id}: {why}.")
        failure = _failure_text(before)
        rep.log(FIXER, f"Reproduction fails as expected before the fix: {before.failure_lines(1)[0][:160]}")

        try:
            return _fix_loop(rep, ws, runner, finding, pr, db_path, finding_id, reqs, max_attempts,
                             repro_test_file, repro_test_code, adversarial_file, baseline, failure)
        except Exception:
            rep.status("proven", "Fix & verify crashed; finding returned to PROVEN")
            raise
    finally:
        if os.environ.get("PROOFPR_KEEP_WORKSPACE") != "1":
            _rmtree(tmpdir)


def _fix_loop(rep, ws, runner, finding, pr, db_path, finding_id, reqs, max_attempts,
              repro_test_file, repro_test_code, adversarial_file, baseline, failure) -> FixVerifyResult:
    feedback: list[str] | None = None
    suite: AdversarialSuite | None = None
    adversarial_unavailable = ""
    attempt_log: list[str] = []
    last = dict(diff="", summary="", repro=None, adv=None, reg=None)

    for attempt in range(1, max_attempts + 1):
        rep.status("fixing", f"Fixer attempt {attempt}")
        rep.start(FIXER, f"Generating minimal patch (attempt {attempt})")
        _git(ws, "checkout", "--", ".")
        sources = _source_files(ws, finding["file"], repro_test_file)
        try:
            proposal: FixProposal = run_fixer_agent(
                title=finding["title"], claim=finding["claim"], description=finding["description"] or "",
                source_files=sources, repro_test_file=repro_test_file, repro_test_code=repro_test_code,
                repro_failure=failure, repo_dir=ws, requirements=reqs, feedback=feedback,
                file=finding["file"], line=finding["line"],
            )
            apply_edits(ws, proposal)
        except (FixerAgentError, PatchApplyError) as exc:
            note = f"Attempt {attempt}: no applicable patch — {exc}"
            attempt_log.append(note)
            rep.finish(FIXER, note, ok=False)
            feedback = [str(exc)]
            continue
        diff = _git(ws, "diff").stdout
        last.update(diff=diff, summary=proposal.summary)
        _save_patch(finding_id, diff, "pending", db_path)
        rep.finish(FIXER, f"Patch generated: {proposal.summary}")

        rep.status("verifying", f"Verifying fix attempt {attempt}")
        repro_after = run_tests(ws, runner, [repro_test_file])
        last.update(repro=repro_after, adv=None, reg=None)
        if not repro_after.ok:
            if repro_after.failed:
                feedback = ["Reproduction test still fails: " + _failure_text(repro_after)]
                why = "reproduction still fails"
            else:
                feedback = ["Your patch does not compile or the test can no longer run: " + _failure_text(repro_after)]
                why = "patch breaks compilation"
            attempt_log.append(f"Attempt {attempt} rejected: {why}")
            rep.log(FIXER, f"Patch rejected: {why}", "error")
            _save_patch(finding_id, diff, "failed", db_path)
            continue
        rep.log(FIXER, "Reproduction test PASSES after the patch", "success")

        rep.start(ADVERSARIAL, f"Trying to break the fix (attempt {attempt})")
        if suite is None and not adversarial_unavailable:
            suite, adversarial_unavailable = _build_suite(
                rep, ws, runner, finding, diff, repro_test_file, repro_test_code, adversarial_file, reqs,
            )
        if suite is not None:
            (ws / suite.test_file).write_text(suite.test_code, encoding="utf-8")
            adv = run_tests(ws, runner, [suite.test_file])
            last["adv"] = adv
            for c in adv.cases:
                rep.log(ADVERSARIAL, f"{'✓' if c.status == 'pass' else '✕'} {c.name}",
                        "success" if c.status == "pass" else "error")
            if adv.failed:
                fails = [f"{c.name}: {c.message[:300]}" for c in adv.cases if c.status == "fail"]
                feedback = ["Adversarial test failed — " + f for f in fails]
                attempt_log.append(f"Attempt {attempt} broken by adversarial test: {fails[0][:200]}")
                rep.finish(ADVERSARIAL, f"Fix BROKEN: {adv.failed} of {len(adv.cases)} edge cases fail", ok=False)
                _save_patch(finding_id, diff, "failed", db_path)
                continue
            rep.finish(ADVERSARIAL, f"{adv.passed}/{len(adv.cases)} adversarial tests pass")
        else:
            rep.finish(ADVERSARIAL, f"No runnable adversarial suite: {adversarial_unavailable}", ok=False)

        rep.start(REGRESSION, f"Running existing suite against the patch (attempt {attempt})")
        reg = run_regression_agent(ws, runner, baseline)
        last["reg"] = reg
        if not reg.ok:
            feedback = [f"Existing test broke: {tid}" for tid in reg.newly_failing] or [reg.patched.error[:400]]
            attempt_log.append(f"Attempt {attempt} rejected by regression: {reg.summary}")
            rep.finish(REGRESSION, f"Regression: {reg.summary}", ok=False)
            _save_patch(finding_id, diff, "failed", db_path)
            continue
        rep.finish(REGRESSION, reg.summary)

        _save_patch(finding_id, diff, "verified", db_path)
        attempt_log.append(f"Attempt {attempt} verified")
        return _conclude(
            rep, finding_id, db_path, "proven_fixed", attempt, last, suite, adversarial_unavailable,
            repro_test_file, attempt_log,
        )

    return _conclude(
        rep, finding_id, db_path, "fix_failed", max_attempts, last, suite, adversarial_unavailable,
        repro_test_file, attempt_log,
    )


def _build_suite(rep, ws, runner, finding, diff, repro_file, repro_code, adv_file, reqs):
    patched_sources = _source_files(ws, finding["file"], repro_file)
    try:
        suite = run_adversarial_agent(
            title=finding["title"], claim=finding["claim"], patch_diff=diff, source_files=patched_sources,
            repro_test_file=repro_file, repro_test_code=repro_code, test_file=adv_file, runner=runner,
            requirements=reqs,
        )
    except AdversarialAgentError as exc:
        return None, f"generation failed: {exc}"
    rep.log(ADVERSARIAL, f"Generated {len(suite.cases) or 'a suite of'} edge-case tests → {suite.test_file}")
    (ws / suite.test_file).write_text(suite.test_code, encoding="utf-8")
    probe = run_tests(ws, runner, [suite.test_file])
    if probe.cases and probe.errors == 0:
        return suite, ""
    rep.log(ADVERSARIAL, "Adversarial suite does not run — repairing it", "warning")
    try:
        suite = repair_adversarial_suite(suite, _failure_text(probe), patched_sources, repro_code)
    except AdversarialAgentError as exc:
        return None, f"repair failed: {exc}"
    (ws / suite.test_file).write_text(suite.test_code, encoding="utf-8")
    probe = run_tests(ws, runner, [suite.test_file])
    if probe.cases and not all(c.status == "error" for c in probe.cases):
        return suite, ""
    (ws / suite.test_file).unlink(missing_ok=True)
    return None, "suite still does not compile after repair: " + _failure_text(probe)[:300]


def _conclude(rep, finding_id, db_path, status, attempts, last, suite, adversarial_unavailable,
              repro_file, attempt_log) -> FixVerifyResult:
    adv: SuiteRun | None = last["adv"]
    reg: RegressionResult | None = last["reg"]
    repro: SuiteRun | None = last["repro"]
    _save_tests(finding_id, db_path, repro, repro_file, adv, suite.cases if suite else [], reg)

    for note in attempt_log:
        _save_evidence(finding_id, "agent_reasoning", "Fix & verify attempt", note, db_path)
    if adv is not None:
        _save_evidence(finding_id, "adversarial",
                       f"Adversarial verification: {adv.passed}/{len(adv.cases)} edge cases pass",
                       suite.test_code if suite else "", db_path, file=suite.test_file if suite else None)
    elif adversarial_unavailable:
        _save_evidence(finding_id, "adversarial", "Adversarial suite unavailable", adversarial_unavailable, db_path)
    if reg is not None:
        _save_evidence(finding_id, "regression", reg.summary,
                       "\n".join(reg.newly_failing) or reg.patched.output[-1500:], db_path)

    if status == "proven_fixed":
        summary = ("Reproduced before the patch and passes after it; "
                   + (f"{adv.passed}/{len(adv.cases)} adversarial checks pass; " if adv else
                      "adversarial suite unavailable; ")
                   + f"{reg.summary if reg else 'regression not run'}.")
        if attempts > 1:
            summary += f" Verified on attempt {attempts}."
    else:
        summary = f"The defect is real but no fix survived verification after {attempts} attempt(s)."
    rep.status(status, summary)

    return FixVerifyResult(
        finding_id=finding_id,
        final_status=status,
        attempts=attempts,
        patch_diff=last["diff"],
        patch_summary=last["summary"],
        reproduction_passes=bool(repro and repro.ok),
        adversarial=(
            {"passed": adv.passed, "total": len(adv.cases), "cases": suite.cases if suite else []} if adv else None
        ),
        regression=(
            {"unit": reg.unit, "integration": reg.integration, "newly_failing": reg.newly_failing,
             "summary": reg.summary} if reg else None
        ),
        summary=summary,
        attempt_log=attempt_log,
    )
