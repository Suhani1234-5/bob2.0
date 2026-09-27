from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import OpenAIError

from agents.requirement_agent import _extract_json, _llm_client, _model

logger = logging.getLogger(__name__)


_SOURCE_CHAR_LIMIT = int(os.environ.get("FIXER_SOURCE_CHAR_LIMIT", "6000"))
_TEST_CHAR_LIMIT = int(os.environ.get("FIXER_TEST_CHAR_LIMIT", "2500"))
_FAILURE_CHAR_LIMIT = int(os.environ.get("FIXER_FAILURE_CHAR_LIMIT", "1200"))
_MAX_TOKENS = int(os.environ.get("FIXER_MAX_TOKENS", "1500"))
_AGENT_NAME = "FixerAgent"


@dataclass
class Edit:
    file: str
    search: str
    replace: str


@dataclass
class FixProposal:
    summary: str
    rationale: str
    edits: list[Edit] = field(default_factory=list)


class FixerAgentError(Exception):
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


class PatchApplyError(Exception):
    pass


def _json_object(text: str) -> dict:
    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def ask_json(system: str, user: str, *, max_tokens: int, temperature: float, agent: str) -> tuple[dict, str]:
    client = _llm_client()
    model = _model()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
        )
    except OpenAIError as exc:
        raise FixerAgentError(f"{agent}: LLM call failed: {exc}") from exc
    raw = (resp.choices[0].message.content or "").strip()
    try:
        return _json_object(raw), raw
    except ValueError as err:
        parse_error = str(err)
        logger.warning("%s: attempt 1 parse failed (%s) — retrying", agent, parse_error)

    messages += [
        {"role": "assistant", "content": raw},
        {"role": "user", "content": (
            f"Your previous response was not valid JSON ({parse_error}). "
            "Respond with ONLY the JSON object described in the instructions. No other text."
        )},
    ]
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.0, max_tokens=max_tokens,
        )
    except OpenAIError as exc:
        raise FixerAgentError(f"{agent}: LLM recovery call failed: {exc}", raw_response=raw) from exc
    raw2 = (resp.choices[0].message.content or "").strip()
    try:
        return _json_object(raw2), raw2
    except ValueError as exc:
        raise FixerAgentError(f"{agent}: no valid JSON after 2 attempts: {exc}", raw_response=raw2) from exc


_SYSTEM_PROMPT = """\
You are the Fixer Agent for ProofPR. A reproduction test has PROVEN a bug in a \
pull request. Write the SMALLEST code change that fixes the bug so the \
reproduction test passes.

RULES:
1. Respond with ONLY a JSON object — no markdown fences, no prose.
2. Schema:
   {
     "summary":   "<one line describing the change>",
     "rationale": "<1-2 sentences: why this is the minimal correct fix>",
     "edits": [
       {"file": "<path of a SOURCE file shown to you>",
        "search": "<exact text copied from that file, 1-6 whole lines>",
        "replace": "<the new text for those lines>"}
     ]
   }
3. "search" must be copied EXACTLY (same characters and indentation) from the \
   file and must appear only once in it. Include enough lines to be unique. \
   Do NOT include the ">>" markers or any line numbers.
4. Never edit test files. Change production code only.
5. Minimal change: preserve the architecture, follow the existing style, reuse \
   existing helpers (e.g. an existing validation method) instead of duplicating \
   logic, no unrelated refactoring.
6. Fix the root cause for all inputs, not just the one in the test.
"""


def _build_user_message(
    title: str,
    claim: str,
    description: str,
    requirements: list[str],
    source_files: dict[str, str],
    repro_test_file: str,
    repro_test_code: str,
    repro_failure: str,
    feedback: list[str] | None,
    file: Optional[str] = None,
    line: Optional[int] = None,
) -> str:
    lines = [f"## Finding: {title}", f"Claim: {claim}"]
    if description:
        lines.append(f"Reasoning: {description}")
    if file:
        lines.append(f"Location: {file}" + (f":{line}" if line else ""))
        focus = _focus(source_files.get(file, ""), line)
        if focus:
            lines += ["The defect is here (>> marks the reported line). Fix THIS code path:", "```", focus, "```"]
    if requirements:
        lines.append("Requirements:")
        lines += [f"- {r}" for r in requirements]
    lines.append("")

    budget = _SOURCE_CHAR_LIMIT
    for path, content in source_files.items():
        if budget <= 0:
            break
        chunk = content[:budget]
        budget -= len(chunk)
        lines += [f"### {path}", "```", chunk + ("\n// [...truncated]" if len(chunk) < len(content) else ""), "```", ""]

    lines += [
        f"### Reproduction test ({repro_test_file}) — must PASS after your fix",
        "```", repro_test_code[:_TEST_CHAR_LIMIT], "```", "",
        "### Current failure", "```", repro_failure[:_FAILURE_CHAR_LIMIT], "```", "",
    ]
    if feedback:
        lines.append("### Your previous fix was REJECTED by verification. Failing checks:")
        lines += [f"- {f[:400]}" for f in feedback[:8]]
        lines += ["Address the root cause of these failures.", ""]
    lines.append("Return ONLY the JSON object.")
    return "\n".join(lines)


def _focus(content: str, line: Optional[int], radius: int = 6) -> str:
    if not content or not line:
        return ""
    rows = content.split("\n")
    lo, hi = max(0, line - 1 - radius), min(len(rows), line + radius)
    return "\n".join((">> " if i == line - 1 else "   ") + rows[i] for i in range(lo, hi))


def _parse_edits(data: dict) -> FixProposal:
    raw_edits = data.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        raise ValueError("'edits' must be a non-empty list")
    edits = []
    for i, e in enumerate(raw_edits):
        if not isinstance(e, dict):
            raise ValueError(f"edit #{i} is not an object")
        f, s, r = e.get("file"), e.get("search"), e.get("replace")
        if not isinstance(f, str) or not isinstance(s, str) or not isinstance(r, str) or not s.strip():
            raise ValueError(f"edit #{i} needs string 'file', non-empty 'search' and 'replace'")
        edits.append(Edit(file=f.strip().lstrip("./").replace("\\", "/"), search=s, replace=r))
    return FixProposal(
        summary=str(data.get("summary", "")).strip() or "Proposed fix",
        rationale=str(data.get("rationale", "")).strip(),
        edits=edits,
    )


def _normalise(text: str) -> str:
    return text.replace("\r\n", "\n")


def _locate(text: str, search: str) -> tuple[int, int, str] | int:
    exact = text.count(search)
    if exact == 1:
        start = text.index(search)
        return start, start + len(search), ""
    if exact > 1:
        return exact

    want = [l.strip() for l in search.strip("\n").split("\n")]
    if not any(want):
        return 0
    lines = text.split("\n")
    stripped = [l.strip() for l in lines]
    hits = [i for i in range(len(lines) - len(want) + 1) if stripped[i:i + len(want)] == want]
    if len(hits) != 1:
        return len(hits)
    i = hits[0]
    start = sum(len(l) + 1 for l in lines[:i])
    end = start + len("\n".join(lines[i:i + len(want)]))
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    return start, end, indent


def _reindent(replace: str, search: str, indent: str) -> str:
    first = next((l for l in search.split("\n") if l.strip()), "")
    model_indent = first[: len(first) - len(first.lstrip())]
    out = []
    for line in replace.strip("\n").split("\n"):
        body = line[len(model_indent):] if line.startswith(model_indent) else line.lstrip()
        out.append(indent + body if line.strip() else line)
    return "\n".join(out)


def check_edits(repo_dir: str | Path, proposal: FixProposal) -> list[str]:
    problems = []
    for e in proposal.edits:
        path = Path(repo_dir) / e.file
        if e.file.startswith("tests/") or ".test." in e.file or ".spec." in e.file:
            problems.append(f"{e.file}: test files must not be edited")
            continue
        if not path.is_file():
            problems.append(f"{e.file}: file does not exist")
            continue
        found = _locate(_normalise(path.read_text(encoding="utf-8")), _normalise(e.search))
        if isinstance(found, int):
            problems.append(f"{e.file}: search block matched {found} times (must match exactly once)")
    return problems


def apply_edits(repo_dir: str | Path, proposal: FixProposal) -> None:
    problems = check_edits(repo_dir, proposal)
    if problems:
        raise PatchApplyError("; ".join(problems))
    for e in proposal.edits:
        path = Path(repo_dir) / e.file
        raw = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        text = _normalise(raw)
        found = _locate(text, _normalise(e.search))
        if isinstance(found, int):
            raise PatchApplyError(f"{e.file}: search block matched {found} times after previous edits")
        start, end, indent = found
        replacement = _normalise(e.replace)
        if indent:
            replacement = _reindent(replacement, _normalise(e.search), indent)
        text = text[:start] + replacement + text[end:]
        if crlf:
            text = text.replace("\n", "\r\n")
        path.write_bytes(text.encode("utf-8"))


def run_fixer_agent(
    title: str,
    claim: str,
    description: str,
    source_files: dict[str, str],
    repro_test_file: str,
    repro_test_code: str,
    repro_failure: str,
    repo_dir: str | Path,
    requirements: Optional[list[str]] = None,
    feedback: Optional[list[str]] = None,
    file: Optional[str] = None,
    line: Optional[int] = None,
) -> FixProposal:
    user = _build_user_message(
        title, claim, description, requirements or [], source_files,
        repro_test_file, repro_test_code, repro_failure, feedback, file, line,
    )
    logger.info("FixerAgent: requesting fix (model=%s, %d chars)", _model(), len(user))
    data, raw = ask_json(_SYSTEM_PROMPT, user, max_tokens=_MAX_TOKENS, temperature=0.0, agent=_AGENT_NAME)

    for round_no in (1, 2):
        try:
            proposal = _parse_edits(data)
            problems = check_edits(repo_dir, proposal)
        except ValueError as exc:
            problems = [str(exc)]
            proposal = None
        if not problems and proposal is not None:
            return proposal
        if round_no == 2:
            break
        logger.warning("FixerAgent: edits invalid (%s) — asking for correction", "; ".join(problems))
        correction = (
            user
            + "\n\n### Your edits could not be applied:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nCopy each 'search' block EXACTLY from the file contents above. Return the corrected JSON only."
        )
        data, raw = ask_json(_SYSTEM_PROMPT, correction, max_tokens=_MAX_TOKENS, temperature=0.0, agent=_AGENT_NAME)

    raise FixerAgentError(f"Fixer produced no applicable edits: {'; '.join(problems)}", raw_response=raw)
