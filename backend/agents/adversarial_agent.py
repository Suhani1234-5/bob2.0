from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from agents.fixer_agent import FixerAgentError, ask_json

logger = logging.getLogger(__name__)

_SOURCE_CHAR_LIMIT = int(os.environ.get("ADVERSARIAL_SOURCE_CHAR_LIMIT", "5000"))
_TEST_CHAR_LIMIT = int(os.environ.get("ADVERSARIAL_TEST_CHAR_LIMIT", "2000"))
_MAX_TOKENS = int(os.environ.get("ADVERSARIAL_MAX_TOKENS", "2000"))
_AGENT_NAME = "AdversarialVerifier"


@dataclass
class AdversarialSuite:
    test_file: str
    test_code: str
    cases: list[str] = field(default_factory=list)


class AdversarialAgentError(Exception):
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


_SYSTEM_PROMPT = """\
You are the Adversarial Verifier for ProofPR. A Fixer agent has patched a bug. \
Do NOT assume the fix is correct: your job is to BREAK it.

Write a {runner} test file (TypeScript) with 5-8 focused tests for the inputs \
most likely to make the fix fail:
- exact boundaries (==, 0, 1, N, N+1, "now")
- null / undefined / empty values
- timezone offsets and clock boundaries for time logic
- combinations with other rules (e.g. disabled AND expired)
- side effects that must NOT happen on the rejection path
- the same behaviour through the public entry point, not only the helper
- ordinary valid inputs that must keep working (no over-correction)

Assert the behaviour REQUIRED by the finding and requirements, not whatever \
the patch happens to do.

RULES:
1. Respond with ONLY a JSON object — no markdown fences, no prose.
2. Schema:
   {{
     "test_code": "<complete test file content>",
     "cases": ["<short label per test, same order as the tests>"]
   }}
3. Import ONLY names that exist in the source shown, using the same relative \
   import paths as the reproduction test (the file lives next to it).
4. Deterministic: no network, no randomness, no real timers. Inject a fixed \
   clock the way the reproduction test does.
"""

_REPAIR_PROMPT = """\
You are the Adversarial Verifier for ProofPR. Your previous test file did not \
run (compile/import error), so it proved nothing. Fix it so it runs. Keep the \
same scenarios and assertions. Import only names that exist in the source \
shown. Respond with ONLY the JSON object {"test_code": "...", "cases": [...]}.
"""


def _source_block(source_files: dict[str, str]) -> list[str]:
    lines, budget = [], _SOURCE_CHAR_LIMIT
    for path, content in source_files.items():
        if budget <= 0:
            break
        chunk = content[:budget]
        budget -= len(chunk)
        lines += [f"### {path} (patched)", "```", chunk, "```", ""]
    return lines


def _build_user_message(
    title: str,
    claim: str,
    requirements: list[str],
    patch_diff: str,
    source_files: dict[str, str],
    repro_test_file: str,
    repro_test_code: str,
) -> str:
    lines = [f"## Finding: {title}", f"Claim: {claim}"]
    if requirements:
        lines.append("Requirements:")
        lines += [f"- {r}" for r in requirements]
    lines += ["", "### Proposed patch", "```diff", patch_diff[:2500], "```", ""]
    lines += _source_block(source_files)
    lines += [
        f"### Reproduction test ({repro_test_file}) — follow its imports and setup style",
        "```", repro_test_code[:_TEST_CHAR_LIMIT], "```", "",
        "Return ONLY the JSON object.",
    ]
    return "\n".join(lines)


def _to_suite(data: dict, test_file: str) -> AdversarialSuite:
    code = str(data.get("test_code", "")).strip()
    if not code:
        raise ValueError("'test_code' is missing or empty")
    if not re.search(r"\b(it|test)\s*\(", code):
        raise ValueError("test_code contains no it()/test() calls")
    cases = data.get("cases") or []
    if not isinstance(cases, list):
        cases = [str(cases)]
    return AdversarialSuite(test_file=test_file, test_code=code + "\n", cases=[str(c) for c in cases])


def run_adversarial_agent(
    title: str,
    claim: str,
    patch_diff: str,
    source_files: dict[str, str],
    repro_test_file: str,
    repro_test_code: str,
    test_file: str,
    runner: str = "jest",
    requirements: Optional[list[str]] = None,
) -> AdversarialSuite:
    user = _build_user_message(
        title, claim, requirements or [], patch_diff, source_files, repro_test_file, repro_test_code,
    )
    system = _SYSTEM_PROMPT.format(runner="Vitest" if runner == "vitest" else "Jest")
    logger.info("AdversarialVerifier: generating suite (%d chars)", len(user))
    try:
        data, raw = ask_json(system, user, max_tokens=_MAX_TOKENS, temperature=0.3, agent=_AGENT_NAME)
        return _to_suite(data, test_file)
    except FixerAgentError as exc:
        raise AdversarialAgentError(str(exc), exc.raw_response) from exc
    except ValueError as exc:
        raise AdversarialAgentError(f"Invalid adversarial suite: {exc}", raw) from exc


def repair_adversarial_suite(
    suite: AdversarialSuite,
    error_output: str,
    source_files: dict[str, str],
    repro_test_code: str,
) -> AdversarialSuite:
    user = "\n".join(
        [
            f"### Your previous test file ({suite.test_file})",
            "```", suite.test_code[:4000], "```", "",
            "### Error", "```", error_output[-1500:], "```", "",
            *_source_block(source_files),
            "### Working reproduction test (copy its imports)",
            "```", repro_test_code[:_TEST_CHAR_LIMIT], "```",
        ]
    )
    try:
        data, raw = ask_json(_REPAIR_PROMPT, user, max_tokens=_MAX_TOKENS, temperature=0.0, agent=_AGENT_NAME)
        return _to_suite(data, suite.test_file)
    except FixerAgentError as exc:
        raise AdversarialAgentError(str(exc), exc.raw_response) from exc
    except ValueError as exc:
        raise AdversarialAgentError(f"Invalid repaired suite: {exc}", raw) from exc
