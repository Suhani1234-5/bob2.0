"""
Reproducer Agent — Phase 6.

Single-responsibility: given one candidate finding (from the Investigator),
generate the *smallest possible* TypeScript/Jest test that should expose
the claimed bug, execute it in a sandboxed subprocess against the PR branch,
and return a structured result.

The agent DOES NOT fix anything.  Its only job is to answer:
    "Can we actually reproduce the claimed bug?"

Scope constraint (MVP)
----------------------
Only Node.js / TypeScript repos are supported.  The repo must have:
  - package.json  (at repo root)
  - A test runner already configured: Jest or Vitest
    (detected by inspecting package.json scripts / devDependencies)

Sandbox model
-------------
No Docker is required.  The sandbox is a plain OS subprocess with:
  - a fresh temp directory (deleted after the run)
  - a shallow git clone of the repo
  - PR branch checked out
  - `npm ci` (or `npm install` fallback) to install deps
  - only the GENERATED test file is executed (not the full suite)
  - a hard wall-clock timeout (default 120 s)

Machine requirements:
  - Node.js ≥ 18  on PATH  (`node --version` to verify)
  - npm           on PATH  (`npm --version` to verify)
  - git           on PATH  (`git --version` to verify)
  - network access to clone from GitHub (token used if GITHUB_TOKEN is set)

State-machine rules (from PRD §10)
------------------------------------
After execution the finding status is updated:

  test exits NON-ZERO  +  output matches the claim keyword  →  PROVEN
  test exits ZERO (passes when it should fail)               →  NOT_REPRODUCED → REJECTED
  subprocess error / timeout / missing tooling               →  UNVERIFIED

LLM configuration
-----------------
Re-uses BOB_API_BASE / BOB_API_KEY / BOB_MODEL from requirement_agent.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import OpenAI, OpenAIError

from agents.requirement_agent import _llm_client, _model, _extract_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SANDBOX_TIMEOUT_SECS: int = int(os.environ.get("REPRODUCER_TIMEOUT", "120"))
_SOURCE_CHAR_LIMIT    = 8_000   # chars of source sent to LLM per file
_AGENT_NAME           = "reproducer"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ReproductionResult:
    """Everything produced by one reproduction run."""
    finding_id:      int
    test_file_path:  str              # relative path inside repo, e.g. tests/proof/42.test.ts
    test_code:       str              # generated TypeScript test content
    command:         str              # npm command that was run
    exit_code:       int | None       # None = never ran (setup failure)
    stdout:          str
    stderr:          str
    execution_time:  float            # seconds
    finding_status:  str              # proven | not_reproduced | unverified
    test_status:     str              # pass | fail | error  (DB TestStatus values)
    expected_result: str
    actual_result:   str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ReproducerAgentError(Exception):
    """Hard failure that prevents reproduction from running at all."""
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Reproducer Agent for ProofPR. Your sole job is to generate the \
SMALLEST possible TypeScript test that, when run against the UNCHANGED source \
code, should FAIL in a way that confirms the suspected bug.

RULES:
1. Respond with ONLY a JSON object — no markdown fences, no prose.
2. The JSON must match this exact schema:
   {
     "test_code":       "<full TypeScript test file content as a string>",
     "expected_result": "<one sentence: what the test expects to happen>",
     "test_file_name":  "<filename only, e.g. finding-42.proof.test.ts>"
   }
3. The test must use the test runner already present in the repo (prefer \
   Jest; use Vitest if jest is absent from package.json).
4. Import ONLY from files that exist in the provided source listing.
5. The test should be self-contained and deterministic.
6. Do NOT use external network calls, random data, or timers.
7. The test MUST fail (i.e. the assertion fails) when the bug is present, \
   and PASS after the bug is fixed.
8. Keep the test under 60 lines.
"""

_RECOVERY_SYSTEM_PROMPT = """\
You are the Reproducer Agent for ProofPR. Your previous response was not \
valid JSON. Return ONLY the JSON object with keys: \
"test_code", "expected_result", "test_file_name". No other text.
"""


def _build_user_message(
    finding_id: int,
    title: str,
    claim: str,
    description: str,
    file: Optional[str],
    line: Optional[int],
    source_files: dict[str, str],    # path → content
    package_json: Optional[str],
) -> str:
    lines: list[str] = []
    lines.append(f"## Finding #{finding_id}: {title}")
    lines.append(f"**Claim:** {claim}")
    lines.append(f"**Reasoning:** {description}")
    if file:
        loc = f"{file}:{line}" if line else file
        lines.append(f"**Location:** {loc}")
    lines.append("")

    if package_json:
        pkg_preview = package_json[:1500]
        lines.append("### package.json (first 1500 chars)")
        lines.append("```json")
        lines.append(pkg_preview)
        lines.append("```")
        lines.append("")

    if source_files:
        lines.append("### Relevant source files")
        for path, content in source_files.items():
            truncated = content[:_SOURCE_CHAR_LIMIT]
            if len(content) > _SOURCE_CHAR_LIMIT:
                truncated += "\n// [...truncated]"
            lines.append(f"#### {path}")
            lines.append("```typescript")
            lines.append(truncated)
            lines.append("```")
            lines.append("")

    lines.append(
        "Generate the smallest TypeScript test that exposes the bug described "
        "above. Return ONLY the JSON object as instructed."
    )
    return "\n".join(lines)


def _recovery_user_message(bad_output: str) -> str:
    return (
        "Your previous response was not valid JSON.\n"
        f"Bad output (first 400 chars):\n---\n{bad_output[:400]}\n---\n"
        "Return ONLY the JSON object now."
    )


# ---------------------------------------------------------------------------
# LLM test generation
# ---------------------------------------------------------------------------

def _generate_test(
    finding_id: int,
    title: str,
    claim: str,
    description: str,
    file: Optional[str],
    line: Optional[int],
    source_files: dict[str, str],
    package_json: Optional[str],
) -> tuple[str, str, str]:
    """
    Call the LLM to produce a reproduction test.

    Returns (test_code, expected_result, test_file_name).
    Raises ReproducerAgentError on hard failures.
    """
    client = _llm_client()
    model  = _model()
    user_msg = _build_user_message(
        finding_id, title, claim, description, file, line,
        source_files, package_json,
    )

    logger.info("ReproducerAgent: generating test for finding #%d (model=%s)", finding_id, model)

    # Attempt 1
    try:
        resp1 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=2048,
        )
    except OpenAIError as exc:
        raise ReproducerAgentError(f"LLM call failed: {exc}") from exc

    raw1 = (resp1.choices[0].message.content or "").strip()
    logger.debug("ReproducerAgent: raw response attempt 1: %s", raw1[:300])

    try:
        return _parse_test_response(raw1)
    except ValueError as e:
        logger.warning("ReproducerAgent: attempt 1 parse failed (%s) — retrying", e)

    # Attempt 2 (recovery)
    try:
        resp2 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",    "content": _RECOVERY_SYSTEM_PROMPT},
                {"role": "user",      "content": user_msg},
                {"role": "assistant", "content": raw1},
                {"role": "user",      "content": _recovery_user_message(raw1)},
            ],
            temperature=0.0,
            max_tokens=2048,
        )
    except OpenAIError as exc:
        raise ReproducerAgentError(
            f"LLM recovery call failed: {exc}", raw_response=raw1
        ) from exc

    raw2 = (resp2.choices[0].message.content or "").strip()
    logger.debug("ReproducerAgent: raw response attempt 2: %s", raw2[:300])

    try:
        return _parse_test_response(raw2)
    except ValueError as exc:
        raise ReproducerAgentError(
            f"ReproducerAgent failed to produce valid JSON after 2 attempts: {exc}",
            raw_response=raw2,
        ) from exc


def _parse_test_response(text: str) -> tuple[str, str, str]:
    """Parse LLM response → (test_code, expected_result, test_file_name)."""
    parsed = _extract_json(text)   # reuse 3-strategy parser from requirement_agent

    test_code = parsed.get("test_code", "").strip()
    if not test_code:
        raise ValueError("'test_code' is missing or empty")

    expected = parsed.get("expected_result", "").strip()
    if not expected:
        raise ValueError("'expected_result' is missing or empty")

    name = parsed.get("test_file_name", "").strip()
    if not name:
        raise ValueError("'test_file_name' is missing or empty")

    # Sanitise filename — strip any directory components the model may sneak in
    name = Path(name).name
    if not name.endswith(".ts"):
        name = name + ".ts"

    return test_code, expected, name


# ---------------------------------------------------------------------------
# Status-machine helpers
# ---------------------------------------------------------------------------

def _decide_status(exit_code: int, stdout: str, stderr: str, claim: str) -> tuple[str, str]:
    """
    Apply PRD §10 state-machine rules.

    Returns (finding_status, test_status) where:
      finding_status ∈ {proven, not_reproduced, unverified}
      test_status    ∈ {pass, fail, error}   (maps to DB TestStatus values)
    """
    combined_output = (stdout + stderr).lower()

    if exit_code is None:
        # sandbox never ran
        return "unverified", "error"

    if exit_code != 0:
        # Test runner reported failures — confirm the output is related to
        # the claim and not a setup/syntax error
        if _looks_like_test_failure(combined_output):
            return "proven", "fail"
        else:
            # Non-zero but no recognisable test failure — infra/setup error
            return "unverified", "error"
    else:
        # Exit 0 means all tests passed — the bug was not reproduced
        return "not_reproduced", "pass"


def _looks_like_test_failure(output: str) -> bool:
    """
    Return True if output looks like a genuine test assertion failure
    rather than a tooling/compilation error.
    Jest and Vitest use similar output patterns.
    """
    test_failure_patterns = [
        r"tests? failed",
        r"● ",                       # Jest bullet for failed test
        r"expect\(",                 # Jest/Vitest assertion in output
        r"received",                 # Jest diff line
        r"assertionerror",
        r"fail\b",
        r"\d+ failed",
        r"✗",                        # Vitest
        r"× ",                       # Vitest
    ]
    return any(re.search(p, output, re.IGNORECASE) for p in test_failure_patterns)


# ---------------------------------------------------------------------------
# Sandbox execution
# ---------------------------------------------------------------------------

def _check_tools() -> list[str]:
    """Return a list of missing required executables."""
    missing = []
    for tool in ("git", "node", "npm"):
        if shutil.which(tool) is None:
            missing.append(tool)
    return missing


def _clone_and_checkout(repo: str, branch: str, target_dir: str) -> subprocess.CompletedProcess:
    """Shallow-clone repo and checkout the PR head branch."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        clone_url = f"https://{token}@github.com/{repo}.git"
    else:
        clone_url = f"https://github.com/{repo}.git"

    return subprocess.run(
        ["git", "clone", "--depth=1", "--branch", branch, clone_url, target_dir],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _detect_test_runner(package_json_text: str) -> str:
    """Return 'vitest' if vitest is in devDependencies/scripts, else 'jest'."""
    lower = package_json_text.lower()
    if "vitest" in lower:
        return "vitest"
    return "jest"


def _install_deps(repo_dir: str) -> subprocess.CompletedProcess:
    """Run npm ci; fall back to npm install if ci fails (no lockfile)."""
    result = subprocess.run(
        ["npm", "ci", "--prefer-offline"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["npm", "install"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
    return result


def _run_test_file(repo_dir: str, test_file_rel: str, runner: str) -> tuple[int, str, str, float]:
    """
    Run a single test file via the configured runner.

    Returns (exit_code, stdout, stderr, elapsed_seconds).
    """
    if runner == "vitest":
        cmd = ["npx", "vitest", "run", test_file_rel, "--reporter=verbose"]
    else:
        cmd = ["npx", "jest", "--testPathPattern", re.escape(test_file_rel),
               "--no-coverage", "--forceExit"]

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=_SANDBOX_TIMEOUT_SECS,
        )
        elapsed = time.monotonic() - start
        return proc.returncode, proc.stdout, proc.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return 1, "", f"Timed out after {_SANDBOX_TIMEOUT_SECS}s", elapsed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_reproducer_agent(
    finding_id:   int,
    title:        str,
    claim:        str,
    description:  str,
    file:         Optional[str],
    line:         Optional[int],
    repo:         str,       # "owner/repo"
    branch:       str,       # PR head branch
    source_files: dict[str, str],   # path → content fetched from GitHub
    package_json: Optional[str],
) -> ReproductionResult:
    """
    Generate a reproduction test and execute it in a sandbox.

    Steps
    -----
    1. Check that git/node/npm exist on PATH.
    2. Ask the LLM to generate a TypeScript test file.
    3. Clone the repo (shallow, PR branch) into a temp dir.
    4. Write the generated test into tests/proof/<name>.
    5. npm ci (or npm install).
    6. Run only the generated test file.
    7. Interpret exit code + output → finding_status / test_status.
    8. Clean up temp dir.
    9. Return ReproductionResult.

    Raises ReproducerAgentError only for LLM failures.  Sandbox failures
    (missing tools, clone error, install error) are captured inside the
    result with test_status="error" / finding_status="unverified".
    """
    # ── 1. Tooling check ────────────────────────────────────────────────────
    missing = _check_tools()
    if missing:
        msg = f"Missing required tools: {', '.join(missing)}"
        logger.error("ReproducerAgent: %s", msg)
        return ReproductionResult(
            finding_id=finding_id,
            test_file_path="",
            test_code="",
            command="",
            exit_code=None,
            stdout="",
            stderr=msg,
            execution_time=0.0,
            finding_status="unverified",
            test_status="error",
            expected_result="",
            actual_result=msg,
        )

    # ── 2. Generate test ────────────────────────────────────────────────────
    test_code, expected_result, test_file_name = _generate_test(
        finding_id, title, claim, description, file, line,
        source_files, package_json,
    )

    # ── 3-8. Sandbox execution ──────────────────────────────────────────────
    tmpdir = tempfile.mkdtemp(prefix="proofpr_")
    repo_dir = os.path.join(tmpdir, "repo")
    test_rel = f"tests/proof/{test_file_name}"
    command  = f"npx jest --testPathPattern {test_file_name} --no-coverage --forceExit"

    try:
        # 3. Clone
        logger.info("ReproducerAgent: cloning %s branch=%s → %s", repo, branch, repo_dir)
        clone_result = _clone_and_checkout(repo, branch, repo_dir)
        if clone_result.returncode != 0:
            err = f"git clone failed:\n{clone_result.stderr[:800]}"
            logger.error("ReproducerAgent: %s", err)
            return ReproductionResult(
                finding_id=finding_id,
                test_file_path=test_rel,
                test_code=test_code,
                command=command,
                exit_code=None,
                stdout=clone_result.stdout,
                stderr=err,
                execution_time=0.0,
                finding_status="unverified",
                test_status="error",
                expected_result=expected_result,
                actual_result=err,
            )

        # 4. Write generated test
        test_abs = os.path.join(repo_dir, "tests", "proof", test_file_name)
        os.makedirs(os.path.dirname(test_abs), exist_ok=True)
        Path(test_abs).write_text(test_code, encoding="utf-8")
        logger.info("ReproducerAgent: wrote test to %s", test_abs)

        # Detect runner from cloned package.json
        pkg_path = os.path.join(repo_dir, "package.json")
        pkg_text = Path(pkg_path).read_text(encoding="utf-8") if os.path.exists(pkg_path) else ""
        runner = _detect_test_runner(pkg_text)
        if runner == "vitest":
            command = f"npx vitest run {test_rel} --reporter=verbose"

        # 5. Install deps
        logger.info("ReproducerAgent: running npm install in %s", repo_dir)
        install_result = _install_deps(repo_dir)
        if install_result.returncode != 0:
            err = f"npm install failed:\n{install_result.stderr[:800]}"
            logger.error("ReproducerAgent: %s", err)
            return ReproductionResult(
                finding_id=finding_id,
                test_file_path=test_rel,
                test_code=test_code,
                command=command,
                exit_code=None,
                stdout=install_result.stdout,
                stderr=err,
                execution_time=0.0,
                finding_status="unverified",
                test_status="error",
                expected_result=expected_result,
                actual_result=err,
            )

        # 6. Run test
        logger.info("ReproducerAgent: running test file %s (runner=%s)", test_rel, runner)
        exit_code, stdout, stderr, elapsed = _run_test_file(repo_dir, test_rel, runner)
        logger.info(
            "ReproducerAgent: exit_code=%s elapsed=%.1fs", exit_code, elapsed
        )

        # 7. Interpret
        finding_status, test_status = _decide_status(exit_code, stdout, stderr, claim)

        actual = (
            f"exit_code={exit_code}\n"
            f"--- stdout ---\n{stdout[:2000]}\n"
            f"--- stderr ---\n{stderr[:2000]}"
        )

        return ReproductionResult(
            finding_id=finding_id,
            test_file_path=test_rel,
            test_code=test_code,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            execution_time=elapsed,
            finding_status=finding_status,
            test_status=test_status,
            expected_result=expected_result,
            actual_result=actual,
        )

    finally:
        # 8. Always clean up
        shutil.rmtree(tmpdir, ignore_errors=True)
        logger.info("ReproducerAgent: cleaned up %s", tmpdir)
