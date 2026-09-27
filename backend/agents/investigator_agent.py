"""
Investigator Agent — Phase 5.

Single-responsibility: given the PR diff, changed files, and the Requirement
Agent's output, PROPOSE a list of candidate findings.

The agent does NOT prove, reproduce, or fix anything.  Every finding it
emits has status = "candidate" — a claim that must be verified by later agents.

Output contract (always a list of CandidateFinding):
    [
      {
        "title":              "<short description>",
        "severity":           "critical" | "high" | "medium" | "low",
        "file":               "<relative path>",
        "line":               <int | null>,
        "claim":              "<one-sentence claim about the defect>",
        "description":        "<multi-sentence reasoning summary>"
      },
      ...
    ]

LLM configuration
-----------------
Re-uses the same three env vars as the Requirement Agent:

    BOB_API_BASE   — OpenAI-compatible base URL (Bob LiteLLM proxy)
    BOB_API_KEY    — inference API key  (required)
    BOB_MODEL      — model name (default: "gpt-4o")

Parse strategy
--------------
Same as RequirementAgent: attempt 1 → attempt 2 (recovery) → raise.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI, OpenAIError

from agents.requirement_agent import (
    RequirementResult,
    _llm_client,
    _model,
    _extract_json,
)
from github_client import PRContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

_DIFF_CHAR_LIMIT        = 14_000   # slightly more than requirement agent — full diff matters here
_MAX_FINDINGS           = 10       # cap to prevent runaway lists
_AGENT_NAME             = "investigator"

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class CandidateFinding:
    title:       str
    severity:    str                    # critical | high | medium | low
    file:        Optional[str]
    line:        Optional[int]
    claim:       str
    description: str                    # reasoning summary

    def to_dict(self) -> dict:
        return {
            "title":       self.title,
            "severity":    self.severity,
            "file":        self.file,
            "line":        self.line,
            "claim":       self.claim,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class InvestigatorAgentError(Exception):
    """Raised when the agent cannot produce a valid result."""
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Investigator Agent for ProofPR, an evidence-backed PR verification \
system. Your sole job is to read a pull request diff and propose a list of \
CANDIDATE findings — potential bugs, security issues, requirement violations, \
edge-case failures, or unsafe side effects introduced by the diff.

STRICT RULES:
1. Respond with ONLY a JSON array — no markdown fences, no prose, no \
   explanation, nothing before or after the array.
2. Each element of the array must match this exact schema:
   {
     "title":       "<string: short finding title, max 80 chars>",
     "severity":    "<one of: critical | high | medium | low>",
     "file":        "<string: relative file path from the diff, or null>",
     "line":        <integer: most relevant line number from the diff, or null>,
     "claim":       "<string: one sentence stating the suspected defect>",
     "description": "<string: 2-4 sentence reasoning summary explaining why \
this is suspicious and what evidence in the diff supports it>"
   }
3. Only propose findings for code that actually appears in the diff. \
   Do not invent problems unrelated to the changed lines.
4. Do not attempt to fix or reproduce anything. \
   Findings are CANDIDATES only — they will be verified by other agents.
5. "severity" must be exactly one of: critical, high, medium, low.
6. If you find no issues, return an empty array: []
7. Return at most 10 findings. Prioritise by severity.
"""

_RECOVERY_SYSTEM_PROMPT = """\
You are the Investigator Agent for ProofPR. Your previous response was not a \
valid JSON array. You MUST return ONLY a JSON array of finding objects. \
Nothing before it, nothing after it.

Each object must have exactly these keys:
  "title", "severity", "file", "line", "claim", "description"

"severity" must be one of: critical, high, medium, low.
If there are no findings, return [].
"""

_VALID_SEVERITIES = {"critical", "high", "medium", "low"}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_user_message(ctx: PRContext, req: RequirementResult) -> str:
    lines: list[str] = []

    lines.append(f"## PR: {ctx.repo} #{ctx.pr_number}  —  {ctx.title}")
    lines.append("")

    # Requirement context
    lines.append("### Requirement (from Context Agent)")
    lines.append(f"**Intent:** {req.requirement}")
    if req.acceptance_criteria:
        lines.append("**Acceptance criteria:**")
        for c in req.acceptance_criteria:
            lines.append(f"  - {c}")
    lines.append("")

    # Changed file list
    lines.append(f"### Changed files ({ctx.changed_files_count})")
    for f in ctx.changed_files:
        lines.append(f"- [{f.status}] {f.filename}  (+{f.additions} -{f.deletions})")
    lines.append("")

    # Diff
    diff_text = ctx.diff.strip()
    if len(diff_text) > _DIFF_CHAR_LIMIT:
        diff_text = diff_text[:_DIFF_CHAR_LIMIT] + "\n[...diff truncated for length]"
    lines.append("### Unified diff")
    lines.append("```diff")
    lines.append(diff_text)
    lines.append("```")
    lines.append("")

    lines.append(
        "Investigate the diff above for potential defects. "
        "Return ONLY the JSON array as instructed."
    )

    return "\n".join(lines)


def _recovery_user_message(bad_output: str) -> str:
    return (
        "Your previous response was not a valid JSON array.\n\n"
        f"Bad output (first 500 chars):\n---\n{bad_output[:500]}\n---\n\n"
        "Return ONLY the JSON array now. Nothing else."
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_finding(raw: dict, index: int) -> CandidateFinding:
    """Validate one raw finding dict and return a CandidateFinding."""
    def _req_str(key: str) -> str:
        val = raw.get(key, "")
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Finding[{index}].{key!r} is missing or empty")
        return val.strip()

    title       = _req_str("title")
    claim       = _req_str("claim")
    description = _req_str("description")

    severity_raw = raw.get("severity", "").lower().strip()
    if severity_raw not in _VALID_SEVERITIES:
        # Coerce common variants rather than failing
        severity_raw = "medium"

    file_val = raw.get("file")
    file_val = str(file_val).strip() if file_val else None

    line_val = raw.get("line")
    if line_val is not None:
        try:
            line_val = int(line_val)
        except (TypeError, ValueError):
            line_val = None

    return CandidateFinding(
        title=title[:200],        # hard-cap title length
        severity=severity_raw,
        file=file_val,
        line=line_val,
        claim=claim,
        description=description,
    )


def _parse_findings(text: str) -> list[CandidateFinding]:
    """
    Parse the model's text into a list of CandidateFinding.

    Tries:
      1. Direct json.loads on stripped text.
      2. Strip ```json ... ``` fence.
      3. Regex scan for first [...] array.
    """
    text = text.strip()

    raw_list: list[dict] | None = None

    # Strategy 1 — bare JSON array
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            raw_list = parsed
        elif isinstance(parsed, dict) and "findings" in parsed:
            # model sometimes wraps in {"findings": [...]}
            raw_list = parsed["findings"]
    except json.JSONDecodeError:
        pass

    # Strategy 2 — strip markdown fence
    if raw_list is None:
        fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                raw_list = parsed if isinstance(parsed, list) else parsed.get("findings", [])
            except json.JSONDecodeError:
                pass

    # Strategy 3 — find first [...] block
    if raw_list is None:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    raw_list = parsed
            except json.JSONDecodeError:
                pass

    if raw_list is None:
        raise ValueError(f"No JSON array found in response: {text[:200]!r}")

    findings: list[CandidateFinding] = []
    for i, item in enumerate(raw_list[:_MAX_FINDINGS]):
        if not isinstance(item, dict):
            logger.warning("InvestigatorAgent: finding[%d] is not a dict, skipping", i)
            continue
        try:
            findings.append(_validate_finding(item, i))
        except ValueError as e:
            logger.warning("InvestigatorAgent: finding[%d] invalid (%s), skipping", i, e)

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_investigator_agent(
    ctx: PRContext,
    req: RequirementResult,
) -> list[CandidateFinding]:
    """
    Analyse a PR diff and propose candidate findings.

    Args:
        ctx: PRContext from github_client.fetch_pr_context().
        req: RequirementResult from run_requirement_agent().

    Returns:
        List of CandidateFinding (may be empty if no issues found).

    Raises:
        InvestigatorAgentError: when the LLM call fails or returns
                                unparseable output after one retry.
    """
    client = _llm_client()
    model  = _model()
    user_message = _build_user_message(ctx, req)

    # ---- Attempt 1 ---------------------------------------------------------
    logger.info("InvestigatorAgent: calling LLM (model=%s)", model)
    try:
        response_1 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,
            max_tokens=2048,
        )
    except OpenAIError as exc:
        raise InvestigatorAgentError(f"LLM call failed: {exc}") from exc

    raw_text_1 = (response_1.choices[0].message.content or "").strip()
    logger.debug("InvestigatorAgent: raw response (attempt 1): %s", raw_text_1[:300])

    try:
        findings = _parse_findings(raw_text_1)
        logger.info("InvestigatorAgent: parsed %d finding(s) on attempt 1", len(findings))
        return findings
    except ValueError as parse_err:
        logger.warning(
            "InvestigatorAgent: attempt 1 parse failed (%s) — retrying", parse_err
        )

    # ---- Attempt 2 (recovery) ----------------------------------------------
    logger.info("InvestigatorAgent: sending recovery prompt (model=%s)", model)
    try:
        response_2 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",    "content": _RECOVERY_SYSTEM_PROMPT},
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": raw_text_1},
                {"role": "user",      "content": _recovery_user_message(raw_text_1)},
            ],
            temperature=0.0,
            max_tokens=2048,
        )
    except OpenAIError as exc:
        raise InvestigatorAgentError(
            f"LLM recovery call failed: {exc}", raw_response=raw_text_1
        ) from exc

    raw_text_2 = (response_2.choices[0].message.content or "").strip()
    logger.debug("InvestigatorAgent: raw response (attempt 2): %s", raw_text_2[:300])

    try:
        findings = _parse_findings(raw_text_2)
        logger.info(
            "InvestigatorAgent: parsed %d finding(s) on attempt 2 (recovery)", len(findings)
        )
        return findings
    except ValueError as parse_err:
        raise InvestigatorAgentError(
            f"InvestigatorAgent failed to produce valid JSON after 2 attempts: {parse_err}",
            raw_response=raw_text_2,
        ) from parse_err
