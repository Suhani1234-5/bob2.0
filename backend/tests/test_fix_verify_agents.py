from __future__ import annotations

import json
import os
import shutil
import subprocess
import types
from pathlib import Path

import pytest

import agents.fixer_agent as fixer
import agents.regression_agent as regression
from agents.adversarial_agent import AdversarialAgentError, run_adversarial_agent
from agents.fixer_agent import (
    Edit,
    FixerAgentError,
    FixProposal,
    PatchApplyError,
    apply_edits,
    ask_json,
    check_edits,
    run_fixer_agent,
)
from agents.regression_agent import SuiteRun, TestCaseResult, _parse_report, run_regression_agent

FIXTURE = Path(__file__).parent / "fixtures" / "shop-api-ts"


class FakeLLM:
    def __init__(self, responses: list):
        self.responses = list(responses)
        self.prompts: list[list[dict]] = []
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, model, messages, temperature, max_tokens):
        self.prompts.append(messages)
        item = self.responses.pop(0)
        content = item if isinstance(item, str) else json.dumps(item)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])


@pytest.fixture
def fake_llm(monkeypatch):
    def install(responses):
        llm = FakeLLM(responses)
        monkeypatch.setattr(fixer, "_llm_client", lambda: llm)
        return llm
    return install


SERVICE = "src/coupon.service.ts"


@pytest.fixture
def repo(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_apply_edits_preserves_crlf_line_endings(tmp_path):
    f = tmp_path / "src" / "a.ts"
    f.parent.mkdir()
    f.write_bytes(b"line one\r\nif (x) {\r\n  return 1;\r\n}\r\n")
    proposal = FixProposal("s", "r", [Edit("src/a.ts", "if (x) {\n  return 1;\n}", "if (x && y) {\n  return 2;\n}")])
    apply_edits(tmp_path, proposal)
    assert f.read_bytes() == b"line one\r\nif (x && y) {\r\n  return 2;\r\n}\r\n"


@pytest.mark.parametrize(
    "edit, problem",
    [
        (Edit("src/missing.ts", "x", "y"), "does not exist"),
        (Edit("tests/unit/coupon.service.test.ts", "describe", "x"), "test files must not be edited"),
        (Edit(SERVICE, "no such text anywhere", "x"), "matched 0 times"),
        (Edit(SERVICE, "throw new InvalidCoupon(code);", "x"), "matched 2 times"),
    ],
)
def test_check_edits_rejects_unapplicable_edits(repo, edit, problem):
    problems = check_edits(repo, FixProposal("s", "r", [edit]))
    assert len(problems) == 1 and problem in problems[0]
    with pytest.raises(PatchApplyError):
        apply_edits(repo, FixProposal("s", "r", [edit]))


def test_fixer_gets_one_correction_round_for_bad_search_block(repo, fake_llm):
    good_search = "    return Math.max(0, subtotal - coupon.discount);"
    llm = fake_llm([
        {"summary": "s", "rationale": "r", "edits": [{"file": SERVICE, "search": "return total;", "replace": "x"}]},
        {"summary": "Add expiry check", "rationale": "r",
         "edits": [{"file": SERVICE, "search": good_search, "replace": "    this.validate(code);\n" + good_search}]},
    ])
    proposal = run_fixer_agent(
        title="t", claim="c", description="", source_files={SERVICE: (repo / SERVICE).read_text()},
        repro_test_file="tests/proof/r.test.ts", repro_test_code="test", repro_failure="did not throw",
        repo_dir=repo,
    )
    assert proposal.summary == "Add expiry check"
    assert "matched 0 times" in llm.prompts[1][-1]["content"]


def test_fixer_raises_when_no_applicable_edit(repo, fake_llm):
    bad = {"summary": "s", "rationale": "r", "edits": [{"file": "tests/unit/coupon.service.test.ts", "search": "describe", "replace": "x"}]}
    fake_llm([bad, bad])
    with pytest.raises(FixerAgentError, match="test files must not be edited"):
        run_fixer_agent(
            title="t", claim="c", description="", source_files={}, repro_test_file="t", repro_test_code="",
            repro_failure="", repo_dir=repo,
        )


def test_fixer_prompt_includes_verification_feedback(repo, fake_llm):
    search = "    return Math.max(0, subtotal - coupon.discount);"
    llm = fake_llm([{"summary": "s", "rationale": "r", "edits": [{"file": SERVICE, "search": search, "replace": search}]}])
    run_fixer_agent(
        title="t", claim="c", description="", source_files={}, repro_test_file="t", repro_test_code="",
        repro_failure="", repo_dir=repo, feedback=["Adversarial test failed — expiresAt = now: did not throw"],
    )
    assert "expiresAt = now: did not throw" in llm.prompts[0][1]["content"]


def test_ask_json_recovers_from_prose_and_rejects_arrays(fake_llm):
    fake_llm(["Sure! Here is the fix you asked for.", '```json\n{"ok": true}\n```'])
    data, _ = ask_json("sys", "user", max_tokens=10, temperature=0, agent="t")
    assert data == {"ok": True}

    fake_llm(["[1, 2]", "[3]"])
    with pytest.raises(FixerAgentError):
        ask_json("sys", "user", max_tokens=10, temperature=0, agent="t")


def test_adversarial_suite_is_written_to_the_requested_path(fake_llm):
    fake_llm([{"test_code": 'it("boundary", () => { expect(1).toBe(1); });', "cases": ["boundary"]}])
    suite = run_adversarial_agent(
        title="t", claim="c", patch_diff="diff", source_files={}, repro_test_file="r", repro_test_code="",
        test_file="tests/proof/finding-3.adversarial.test.ts",
    )
    assert suite.test_file == "tests/proof/finding-3.adversarial.test.ts"
    assert suite.cases == ["boundary"]


def test_adversarial_rejects_suite_without_tests(fake_llm):
    fake_llm([{"test_code": "const x = 1;", "cases": []}])
    with pytest.raises(AdversarialAgentError, match="no it"):
        run_adversarial_agent(
            title="t", claim="c", patch_diff="", source_files={}, repro_test_file="r", repro_test_code="",
            test_file="tests/proof/a.test.ts",
        )


def test_parse_jest_report_separates_failures_from_broken_tests(tmp_path):
    report = {"testResults": [
        {"name": str(tmp_path / "tests/unit/a.test.ts"), "status": "failed", "assertionResults": [
            {"fullName": "a passes", "status": "passed", "duration": 5, "failureMessages": []},
            {"fullName": "a fails", "status": "failed", "duration": 7,
             "failureMessages": ["Error: expect(received).toThrow(expected)\n\nReceived function did not throw"]},
            {"fullName": "a is broken", "status": "failed", "failureMessages": ["ReferenceError: foo is not defined"]},
            {"fullName": "a is skipped", "status": "pending", "failureMessages": []},
        ]},
        {"name": str(tmp_path / "tests/proof/b.test.ts"), "status": "failed", "assertionResults": [],
         "message": "● Test suite failed to run\n\nsrc/x.ts:1:10 - error TS2305: Module has no exported member 'Nope'."},
    ]}
    cases = {c.name: c for c in _parse_report(report, tmp_path)}
    assert cases["a passes"].status == "pass" and cases["a passes"].file == "tests/unit/a.test.ts"
    assert cases["a fails"].status == "fail"
    assert cases["a is broken"].status == "error"
    assert "a is skipped" not in cases
    assert cases["<test suite failed to run>"].status == "error"


def _run(*cases: tuple[str, str]) -> SuiteRun:
    return SuiteRun(
        command="npx jest",
        cases=[TestCaseResult(tid, tid.split("::")[0], tid.split("::")[1], st, 0.0) for tid, st in cases],
    )


def test_regression_only_fails_on_tests_that_used_to_pass(monkeypatch):
    baseline = _run(
        ("tests/unit/a.test.ts::keeps passing", "pass"),
        ("tests/unit/a.test.ts::already red", "fail"),
        ("tests/integration/b.test.ts::breaks", "pass"),
    )
    patched = _run(
        ("tests/unit/a.test.ts::keeps passing", "pass"),
        ("tests/unit/a.test.ts::already red", "fail"),
        ("tests/integration/b.test.ts::breaks", "fail"),
    )
    monkeypatch.setattr(regression, "run_tests", lambda *a, **k: patched)
    result = run_regression_agent("repo", "jest", baseline)
    assert result.newly_failing == ["tests/integration/b.test.ts::breaks"]
    assert not result.ok
    assert result.unit == {"passed": 1, "total": 2} and result.integration == {"passed": 0, "total": 1}
    assert "1 already failing before the patch" in result.summary

    patched.cases[2].status = "pass"
    assert run_regression_agent("repo", "jest", baseline).ok


needs_sandbox = pytest.mark.skipif(
    os.environ.get("PROOFPR_SANDBOX_TESTS") != "1" or not (shutil.which("npm") and shutil.which("git")),
    reason="set PROOFPR_SANDBOX_TESTS=1 (needs git, Node.js, npm and network for npm install)",
)


def _git_repo(tmp_path: Path) -> Path:
    src = tmp_path / "origin"
    shutil.copytree(FIXTURE, src, ignore=shutil.ignore_patterns("*.txt"))
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "fixture"], ["checkout", "-q", "-b", "feature/coupon-expiry"]):
        subprocess.run(["git", *cmd], cwd=src, check=True, env=env, capture_output=True)
    return src


def _seed(db, db_path: Path, repo: Path) -> int:
    db.init_db(db_path)
    with db.get_connection(db_path) as c:
        pr_id = c.execute(
            "INSERT INTO pull_requests (repository, pr_number, title, description, branch, base_branch, status) "
            "VALUES (?, 42, 'Add coupon expiration validation', 'A coupon is invalid at or after expiresAt.', "
            "'feature/coupon-expiry', 'main', 'running')",
            (str(repo),),
        ).lastrowid
        fid = c.execute(
            "INSERT INTO findings (pr_id, title, description, severity, file, line, claim, status, created_by_agent) "
            "VALUES (?, 'Expired coupons are accepted at checkout', '', 'high', 'src/coupon.service.ts', 34, "
            "'applyCoupon() never checks expiresAt.', 'proven', 'investigator')",
            (pr_id,),
        ).lastrowid
        c.execute(
            "INSERT INTO evidence (finding_id, type, description, file, content) VALUES (?, 'reproduction', 'repro', ?, ?)",
            (fid, "tests/proof/finding-1.proof.test.ts", (FIXTURE / "finding-1.proof.test.ts.txt").read_text()),
        )
    return fid


_SEARCH = ("    const coupon = this.coupons.get(code.toUpperCase());\n"
           "    if (!coupon || !coupon.enabled) throw new InvalidCoupon(code);\n"
           "    return Math.max(0, subtotal - coupon.discount);")
FIX_BOUNDARY_BUG = {"summary": "Check expiresAt with <", "rationale": "r", "edits": [{"file": SERVICE, "search": _SEARCH, "replace": _SEARCH.replace(
    "    return", "    if (coupon.expiresAt !== null && coupon.expiresAt.getTime() < this.now().getTime()) throw new InvalidCoupon(code);\n    return")}]}
FIX_REUSE_VALIDATE = {"summary": "Reuse validate()", "rationale": "r", "edits": [{"file": SERVICE, "search": _SEARCH,
    "replace": "    const coupon = this.validate(code);\n    return Math.max(0, subtotal - coupon.discount);"}]}
ADVERSARIAL = {"cases": ["expiresAt = now (boundary)", "expiresAt = null"], "test_code": """
import { Coupon, CouponService, InvalidCoupon } from "../../src/coupon.service";
const NOW = new Date("2026-03-14T12:00:00Z");
const svc = (c: Coupon) => new CouponService(new Map([[c.code, c]]), () => NOW);
it("expiresAt = now (boundary)", () => {
  expect(() => svc({ code: "B", enabled: true, discount: 5, expiresAt: NOW }).applyCoupon("B", 50)).toThrow(InvalidCoupon);
});
it("expiresAt = null", () => {
  expect(svc({ code: "D", enabled: true, discount: 5, expiresAt: null }).applyCoupon("D", 50)).toBe(45);
});
"""}


@needs_sandbox
def test_pipeline_retries_after_adversarial_counterexample_and_proves_fix(tmp_path, fake_llm):
    import database as db
    from agents.fix_verify import run_fix_verify

    db_path = tmp_path / "proofpr.db"
    fid = _seed(db, db_path, _git_repo(tmp_path))
    fake_llm([FIX_BOUNDARY_BUG, ADVERSARIAL, FIX_REUSE_VALIDATE])
    events: list[dict] = []

    result = run_fix_verify(fid, db_path=db_path, on_event=events.append)

    assert result.final_status == "proven_fixed"
    assert result.attempts == 2
    assert "Attempt 1 broken by adversarial test" in result.attempt_log[0]
    assert result.adversarial["passed"] == result.adversarial["total"] == 2
    assert result.regression["newly_failing"] == []
    assert "this.validate(code)" in result.patch_diff
    with db.get_connection(db_path) as c:
        assert c.execute("SELECT status FROM findings WHERE id=?", (fid,)).fetchone()[0] == "proven_fixed"
        assert c.execute("SELECT verification_status FROM patches WHERE finding_id=?", (fid,)).fetchone()[0] == "verified"
        types_ = {r[0] for r in c.execute("SELECT test_type FROM test_executions WHERE finding_id=?", (fid,))}
        assert types_ == {"reproduction", "adversarial", "regression"}
    assert {"FixerAgent", "AdversarialVerifier", "RegressionAgent"} <= {e.get("agent") for e in events}


@needs_sandbox
def test_pipeline_marks_fix_failed_when_no_fix_survives(tmp_path, fake_llm):
    import database as db
    from agents.fix_verify import run_fix_verify

    db_path = tmp_path / "proofpr.db"
    fid = _seed(db, db_path, _git_repo(tmp_path))
    fake_llm([FIX_BOUNDARY_BUG, ADVERSARIAL, FIX_BOUNDARY_BUG])

    result = run_fix_verify(fid, db_path=db_path, max_attempts=2)

    assert result.final_status == "fix_failed"
    with db.get_connection(db_path) as c:
        assert c.execute("SELECT status FROM findings WHERE id=?", (fid,)).fetchone()[0] == "fix_failed"
        assert c.execute("SELECT verification_status FROM patches WHERE finding_id=?", (fid,)).fetchone()[0] == "failed"


def test_pipeline_refuses_findings_that_are_not_proven(tmp_path):
    import database as db
    from agents.fix_verify import FixVerifyError, run_fix_verify

    db_path = tmp_path / "proofpr.db"
    fid = _seed(db, db_path, tmp_path)
    db.update_finding_status(fid, "rejected", db_path=db_path)
    with pytest.raises(FixVerifyError, match="Only PROVEN findings"):
        run_fix_verify(fid, db_path=db_path)


def test_edit_with_wrong_indentation_still_applies_and_is_reindented(tmp_path):
    f = tmp_path / "src" / "a.ts"
    f.parent.mkdir()
    f.write_bytes(b"class A {\r\n  run(x: number) {\r\n    if (!x) throw new Error();\r\n    return x;\r\n  }\r\n}\r\n")
    edit = Edit("src/a.ts", "if (!x) throw new Error();\nreturn x;", "if (!x) throw new Error();\nif (x < 0) return 0;\nreturn x;")
    apply_edits(tmp_path, FixProposal("s", "r", [edit]))
    assert f.read_bytes() == (
        b"class A {\r\n  run(x: number) {\r\n    if (!x) throw new Error();\r\n"
        b"    if (x < 0) return 0;\r\n    return x;\r\n  }\r\n}\r\n"
    )


def test_fuzzy_match_must_still_be_unique(repo):
    edit = Edit(SERVICE, "const coupon = this.coupons.get(code.toUpperCase());", "x")
    assert "matched 2 times" in check_edits(repo, FixProposal("s", "r", [edit]))[0]


def test_fixer_prompt_points_at_the_reported_line(repo, fake_llm):
    search = "    return Math.max(0, subtotal - coupon.discount);"
    llm = fake_llm([{"summary": "s", "rationale": "r", "edits": [{"file": SERVICE, "search": search, "replace": search}]}])
    source = (repo / SERVICE).read_text()
    line = source.split("\n").index(search) + 1
    run_fixer_agent(
        title="t", claim="c", description="", source_files={SERVICE: source}, repro_test_file="t",
        repro_test_code="", repro_failure="", repo_dir=repo, file=SERVICE, line=line,
    )
    prompt = llm.prompts[0][1]["content"]
    assert f"Location: {SERVICE}:{line}" in prompt
    assert ">> " + search in prompt
