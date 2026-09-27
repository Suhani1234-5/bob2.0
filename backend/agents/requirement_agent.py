"""
Context / Requirement Agent — Phase 4.

Single-responsibility: given the raw PR context fetched in Phase 3, produce a
structured understanding of what the PR is *supposed to do*.

Output contract (always a RequirementResult):
    {
      "requirement":          "<one-sentence statement of intent>",
      "affected_modules":     ["path/to/file.py", ...],
      "acceptance_criteria":  ["criterion 1", "criterion 2", ...]
    }

LLM integration
---------------
The agent uses the OpenAI-compatible chat completions API, pointed at Bob's
LiteLLM proxy via two environment variables:

    BOB_API_BASE   — full base URL, e.g. "https://proxy.bob.example.com/v1"
                     Falls back to the standard OpenAI endpoint if unset.
    BOB_API_KEY    — inference API key.  Required.
    BOB_MODEL      — model name as recognised by the proxy (default: "gpt-4o").

Parse strategy
--------------
1. Ask the model for JSON only via a strict system prompt and explicit JSON
   schema in the user message.
2. Attempt to parse the raw response.
3. On failure, send one recovery prompt ("your output was not valid JSON …")
   and try once more.
4. If the second attempt also fails, raise RequirementAgentError with the raw
   response attached so callers can inspect it.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI, OpenAIError

from github_client import PRContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_API_BASE = "BOB_API_BASE"
_ENV_API_KEY  = "BOB_API_KEY"
_ENV_MODEL    = "BOB_MODEL"
_DEFAULT_MODEL = "gpt-4o"

# Diff is truncated to this many characters before being sent to the model to
# stay within context limits while still covering most real-world PRs.
_DIFF_CHAR_LIMIT = 12_000
# Issue body is also capped independently.
_ISSUE_BODY_CHAR_LIMIT = 3_000


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class RequirementResult:
    requirement: str
    affected_modules: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "affected_modules": self.affected_modules,
            "acceptance_criteria": self.acceptance_criteria,
        }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class RequirementAgentError(Exception):
    """Raised when the agent cannot produce a valid result."""
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _llm_client() -> OpenAI:
    api_key = os.environ.get(_ENV_API_KEY)
    if not api_key:
        raise RequirementAgentError(
            f"Missing required environment variable: {_ENV_API_KEY}"
        )
    base_url = os.environ.get(_ENV_API_BASE)  # None → openai default
    return OpenAI(api_key=api_key, base_url=base_url)


def _model() -> str:
    return os.environ.get(_ENV_MODEL, _DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Context/Requirement Agent for ProofPR, an evidence-backed PR \
verification system. Your sole job is to analyse a pull request and determine \
what it is SUPPOSED to accomplish.

RULES:
1. Respond with ONLY a single JSON object — no markdown fences, no prose, no \
   explanation, no trailing text.
2. The JSON must match this exact schema:
   {
     "requirement":         "<string: one clear sentence describing the PR intent>",
     "affected_modules":    ["<string: relative file path>", ...],
     "acceptance_criteria": ["<string: testable condition>", ...]
   }
3. "affected_modules" must list only files that appear in the diff.
4. "acceptance_criteria" must be concrete and testable — not vague statements.
5. If information is insufficient, still produce valid JSON with your best \
   inferences; never return anything other than the JSON object.
"""

_RECOVERY_SYSTEM_PROMPT = """\
You are the Context/Requirement Agent for ProofPR. Your previous response was \
not valid JSON. You MUST return ONLY a JSON object matching the schema below \
with no other text whatsoever.

Schema:
{
  "requirement":         "<string>",
  "affected_modules":    ["<string>", ...],
  "acceptance_criteria": ["<string>", ...]
}
"""


def _build_user_message(ctx: PRContext) -> str:
    """Assemble the user message from PRContext fields."""
    lines: list[str] = []

    lines.append(f"## Pull Request: {ctx.repo} #{ctx.pr_number}")
    lines.append(f"**Title:** {ctx.title}")
    lines.append("")

    if ctx.description:
        lines.append("**PR Description:**")
        lines.append(ctx.description.strip())
        lines.append("")

    if ctx.linked_issues:
        lines.append("**Linked Issues:**")
        for issue in ctx.linked_issues:
            lines.append(f"- Issue #{issue.number}: {issue.title} ({issue.state})")
            if issue.body:
                body_preview = issue.body.strip()[:_ISSUE_BODY_CHAR_LIMIT]
                if len(issue.body) > _ISSUE_BODY_CHAR_LIMIT:
                    body_preview += "\n[...truncated]"
                lines.append(f"  {body_preview}")
        lines.append("")

    lines.append(f"**Changed files ({ctx.changed_files_count}):**")
    for f in ctx.changed_files:
        lines.append(f"- [{f.status}] {f.filename}  (+{f.additions} -{f.deletions})")
    lines.append("")

    diff_text = ctx.diff.strip()
    if len(diff_text) > _DIFF_CHAR_LIMIT:
        diff_text = diff_text[:_DIFF_CHAR_LIMIT] + "\n[...diff truncated for length]"
    lines.append("**Unified diff:**")
    lines.append("```diff")
    lines.append(diff_text)
    lines.append("```")
    lines.append("")

    lines.append(
        "Analyse the above context and return the JSON object as specified by "
        "your system instructions."
    )

    return "\n".join(lines)


def _recovery_user_message(bad_output: str) -> str:
    return (
        f"Your previous response was not valid JSON:\n\n"
        f"---\n{bad_output[:500]}\n---\n\n"
        "Please respond now with ONLY the valid JSON object. "
        "Nothing before it, nothing after it."
    )


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """
    Parse JSON from the model response.

    Tries three strategies in order:
      1. Direct json.loads on the stripped text.
      2. Strip a single layer of ```json ... ``` fences (model may add them
         despite instructions).
      3. Regex scan for the first {...} block.
    """
    text = text.strip()

    # Strategy 1 — bare JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2 — strip markdown fence
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3 — find first complete JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in response: {text[:200]!r}")


def _validate_and_build(raw: dict) -> RequirementResult:
    """Validate the parsed dict and coerce into RequirementResult."""
    requirement = raw.get("requirement", "").strip()
    if not requirement:
        raise ValueError("'requirement' field is missing or empty")

    affected = raw.get("affected_modules", [])
    if not isinstance(affected, list):
        affected = [str(affected)]

    criteria = raw.get("acceptance_criteria", [])
    if not isinstance(criteria, list):
        criteria = [str(criteria)]

    return RequirementResult(
        requirement=requirement,
        affected_modules=[str(m).strip() for m in affected if m],
        acceptance_criteria=[str(c).strip() for c in criteria if c],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_requirement_agent(ctx: PRContext) -> RequirementResult:
    """
    Analyse a PRContext and return a RequirementResult.

    Makes one LLM call; if JSON parsing fails, makes exactly one retry with a
    recovery prompt. Raises RequirementAgentError on hard failures.

    Args:
        ctx: Populated PRContext from github_client.fetch_pr_context().

    Returns:
        RequirementResult with requirement, affected_modules, acceptance_criteria.

    Raises:
        RequirementAgentError: when the LLM cannot be reached or returns
                               unparseable output after one retry.
    """
    client = _llm_client()
    model  = _model()
    user_message = _build_user_message(ctx)

    # ---- Attempt 1 ---------------------------------------------------------
    logger.info("RequirementAgent: calling LLM (model=%s)", model)
    try:
        response_1 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,  # deterministic — we want structured output
            max_tokens=1024,
        )
    except OpenAIError as exc:
        raise RequirementAgentError(f"LLM call failed: {exc}") from exc

    raw_text_1 = (response_1.choices[0].message.content or "").strip()
    logger.debug("RequirementAgent: raw response (attempt 1): %s", raw_text_1[:300])

    try:
        parsed = _extract_json(raw_text_1)
        result = _validate_and_build(parsed)
        logger.info("RequirementAgent: parsed successfully on attempt 1")
        return result
    except (ValueError, KeyError) as parse_err:
        logger.warning(
            "RequirementAgent: attempt 1 parse failed (%s) — retrying", parse_err
        )

    # ---- Attempt 2 (recovery) ----------------------------------------------
    logger.info("RequirementAgent: sending recovery prompt (model=%s)", model)
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
            max_tokens=1024,
        )
    except OpenAIError as exc:
        raise RequirementAgentError(
            f"LLM recovery call failed: {exc}", raw_response=raw_text_1
        ) from exc

    raw_text_2 = (response_2.choices[0].message.content or "").strip()
    logger.debug("RequirementAgent: raw response (attempt 2): %s", raw_text_2[:300])

    try:
        parsed = _extract_json(raw_text_2)
        result = _validate_and_build(parsed)
        logger.info("RequirementAgent: parsed successfully on attempt 2 (recovery)")
        return result
    except (ValueError, KeyError) as parse_err:
        raise RequirementAgentError(
            f"RequirementAgent failed to produce valid JSON after 2 attempts: {parse_err}",
            raw_response=raw_text_2,
        ) from parse_err
