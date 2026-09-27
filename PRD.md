ProofPR

Evidence-Backed Multi-Agent PR Verification powered by IBM Bob

Tagline: Don’t just review AI-generated code. Prove the review.

Hackathon: IBM Bob 2.0 Hackathon
Product Type: Developer Tool / Agentic AI Workflow
Primary Domain: Code Review, Testing, Software Quality & Developer Productivity

---

1. Executive Summary

AI coding assistants can generate code and review pull requests quickly, but their review comments are not necessarily correct.

A reviewer may claim:

«“This change can allow an expired coupon to be accepted.”»

But developers still need to determine:

- Is the finding actually true?
- Can the problem be reproduced?
- Which exact code causes it?
- Does the proposed fix solve the problem?
- Did the fix introduce another regression?
- Does the fix survive edge cases?

ProofPR transforms code review from:

AI Opinion → Developer manually investigates

into:

Claim → Evidence → Reproduction → Fix → Adversarial Verification → Regression Testing → Proof

Instead of trusting an AI-generated review comment, ProofPR asks independent IBM Bob agents to investigate, reproduce, fix, challenge and verify each important finding.

Every finding receives an evidence-backed status such as:

PROVEN
PROVEN FIXED
REJECTED
UNVERIFIED

The developer therefore receives not just a review, but a reproducible verification trail.

---

2. Problem Statement

Modern development teams increasingly rely on AI-generated code and AI-assisted code reviews.

This introduces a new problem:

AI can produce plausible but incorrect review findings.

A conventional AI reviewer may:

1. Read the diff.
2. Identify potential issues.
3. Generate review comments.
4. Suggest code changes.

However, a developer still has to determine whether those findings are real.

This creates:

- false-positive review comments
- unnecessary developer investigation
- incorrect automated fixes
- insufficient test coverage
- regressions caused by fixes
- low trust in AI code review
- repeated review cycles

The core problem is therefore no longer simply:

“Can AI review this code?”

It is:

“Can AI prove that its review findings are correct?”

ProofPR is designed around that question.

---

3. Existing Approach

Typical AI code-review workflow:

Pull Request
     ↓
AI reads diff
     ↓
AI generates findings
     ↓
AI suggests fixes
     ↓
Developer decides whether to trust them

Even multi-agent reviewers commonly improve the first part by asking several agents to inspect the PR.

PR
 ↓
Security Agent
Quality Agent
Testing Agent
Regression Agent
 ↓
Combined Review

But agreement between AI agents is not proof.

Multiple agents can still repeat the same incorrect assumption.

---

4. Proposed Solution

ProofPR adds an experimental verification layer.

Pull Request
      ↓
Context & Requirement Analysis
      ↓
Parallel Investigation
      ↓
Candidate Findings
      ↓
Evidence Collection
      ↓
Reproduction Test Generation
      ↓
Can the issue actually be reproduced?
     / \
   YES  NO
   ↓     ↓
PROVEN  REJECTED / UNVERIFIED
   ↓
Generate Fix
   ↓
Rerun Reproduction Test
   ↓
Adversarial Verification
   ↓
Regression Suite
   ↓
Evidence Report

The system does not treat an AI claim as a confirmed defect until evidence supports it.

---

5. Target Users

Primary User — Software Developer

A developer preparing or reviewing a pull request.

Needs:

- quick PR verification
- fewer false positives
- reproducible findings
- automatic test generation
- safer fixes
- understandable evidence

Secondary User — Tech Lead / Maintainer

Needs:

- confidence before merging
- requirement compliance
- regression visibility
- review history
- evidence behind findings

Secondary User — QA Engineer

Needs:

- automatically generated edge cases
- reproduction tests
- regression results
- failed scenarios

---

6. Product Goals

ProofPR should:

1. Detect potential PR defects.
2. Connect findings to concrete code evidence.
3. Reproduce suspected defects whenever possible.
4. reject unsupported findings.
5. Generate fixes for confirmed findings.
6. independently challenge generated fixes.
7. run regression tests.
8. provide an understandable proof trail.
9. reduce manual investigation effort.
10. demonstrate meaningful IBM Bob agent orchestration.

---

7. Non-Goals for Hackathon MVP

The MVP will NOT attempt to:

- replace GitHub/GitLab entirely
- analyze every programming language
- guarantee mathematical correctness of arbitrary programs
- automatically merge production PRs
- perform full enterprise CI/CD management
- replace human code ownership decisions

The MVP focuses on demonstrating the verification workflow extremely well.

---

8. Core Product Principle

Claims are not findings until they have evidence.

Every important claim follows:

CLAIM
  ↓
EVIDENCE
  ↓
REPRODUCTION
  ↓
FIX
  ↓
COUNTER-TEST
  ↓
REGRESSION
  ↓
PROOF

---

9. Agent Architecture

ProofPR uses multiple specialized IBM Bob agents.

Agent 1 — Context / Requirement Agent

Purpose:

Understand what the PR is supposed to accomplish.

Inputs:

- issue description
- PR description
- README
- relevant documentation
- repository conventions
- acceptance criteria
- changed files

Outputs:

{
  "requirement": "Expired coupons must be rejected",
  "affected_modules": ["coupon.service.ts"],
  "acceptance_criteria": [
    "active coupon accepted",
    "expired coupon rejected"
  ]
}

This prevents review without understanding the intended behavior.

---

Agent 2 — Investigator Agent

Purpose:

Inspect changed code for potential problems.

Checks:

- logical bugs
- edge cases
- requirement violations
- error handling
- security problems
- unexpected side effects

Example:

Finding:
Expired coupons may still be accepted.

Evidence:
src/services/coupon.service.ts:84

Reason:
Discount validation checks enabled=true
but does not compare expiresAt with current time.

Important:

This remains a candidate finding.

It has not yet been proven.

---

Agent 3 — Reproducer Agent

Purpose:

Attempt to prove or disprove the Investigator's claim.

It creates the smallest possible test that should expose the claimed bug.

Example:

Input:
coupon.expiry = yesterday

Expected:
CouponRejectedError

Actual:
Coupon accepted

If the test fails because the claimed bad behavior occurs:

CONFIRMED

If the test cannot reproduce it:

NOT REPRODUCED

---

Agent 4 — Fixer Agent

Triggered only for sufficiently verified findings.

Purpose:

Generate the smallest reasonable code change that fixes the confirmed defect.

Principles:

- minimal change
- preserve architecture
- follow repository conventions
- avoid unrelated refactoring

---

Agent 5 — Adversarial Verifier

This is a major ProofPR differentiator.

The verifier does NOT assume that the Fixer is correct.

Its job is to break the proposed fix.

It generates additional scenarios such as:

expiresAt = current timestamp
expiresAt = null
expiresAt = malformed
timezone boundary
disabled coupon
valid future coupon

The verifier asks:

«“What inputs could make this fix fail?”»

---

Agent 6 — Regression Agent

Runs existing repository tests after the fix.

Example:

Unit Tests       34/34 PASS
Integration      12/12 PASS
Generated Tests   7/7 PASS

Total            53/53 PASS

---

Agent 7 — Proof Orchestrator

Coordinates the workflow.

Responsibilities:

- launch agents
- aggregate findings
- avoid duplicate findings
- maintain finding state
- resolve conflicting evidence
- collect test results
- create final proof report

The Orchestrator must not simply majority-vote.

Execution evidence has higher value than agent agreement.

---

10. Finding State Machine

Each finding has a state.

CANDIDATE
    ↓
INVESTIGATING
    ↓
 ┌───────────────┐
 ↓               ↓
PROVEN       NOT REPRODUCED
 ↓               ↓
FIXING        REJECTED /
 ↓            UNVERIFIED
VERIFYING
 ↓
 ┌──────────────┐
 ↓              ↓
PROVEN FIXED   FIX FAILED

Possible final statuses:

PROVEN

The suspected defect was reproduced.

PROVEN FIXED

The defect was reproduced before the fix and cannot be reproduced after the fix; required verification checks also pass.

REJECTED

Available evidence contradicted the original finding.

UNVERIFIED

There was insufficient executable evidence to confidently confirm or reject the claim.

FIX FAILED

The original defect remains or the proposed fix fails verification.

---

11. Evidence Model

Every finding stores:

Finding
├── Claim
├── Severity
├── Source
├── File
├── Lines
├── Reasoning summary
├── Reproduction Test
├── Before-Fix Result
├── Proposed Patch
├── After-Fix Result
├── Adversarial Tests
├── Regression Result
└── Final Status

This becomes the Proof Trail.

---

12. User Flow

Step 1 — Start Verification

User opens ProofPR.

The landing dashboard displays:

ProofPR
Evidence-backed pull request verification

[ GitHub Repository URL                 ]

Pull Request
[ #42 ]

[ Verify Pull Request ]

Optional inputs:

Issue URL
PR description
Requirement document

---

Step 2 — Repository Analysis

ProofPR loads:

- PR metadata
- changed files
- diff
- issue
- documentation
- existing tests

UI:

Analyzing PR #42

✓ Repository loaded
✓ 6 changed files
✓ Issue #31 loaded
✓ 47 existing tests discovered
✓ Project conventions identified

Starting verification...

---

13. Main Dashboard UI

After analysis, the user enters the verification workspace.

┌──────────────────────────────────────────────────────────────┐
│ ProofPR                     Repository: shop-api     PR #42 │
├─────────────┬────────────────────────────────────────────────┤
│             │                                                │
│ Overview    │   PR Verification                              │
│ Findings    │                                                │
│ Agents      │   7 Findings                                   │
│ Tests       │   4 Proven                                     │
│ Changes     │   2 Rejected                                   │
│ Proof Trail │   1 Investigating                              │
│ Report      │                                                │
│             │   Verification Confidence  █████████░ 91%      │
│             │                                                │
│             │   Tests                                        │
│             │   47 existing     8 generated     55 passed    │
│             │                                                │
└─────────────┴────────────────────────────────────────────────┘

---

14. Overview Screen

Top section:

PR #42
Add coupon expiration validation

6 files changed
+143 -27

Verification: RUNNING

Summary cards:

┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│      7      │ │      4      │ │      2      │
│ Findings    │ │ Proven      │ │ Rejected    │
└─────────────┘ └─────────────┘ └─────────────┘

┌─────────────┐
│    55/55    │
│ Tests Pass  │
└─────────────┘

---

15. Live Agent Activity UI

A major visual element for the hackathon demo.

Verification Pipeline

Requirement Agent
████████████████████  COMPLETE
        │
        ▼
 ┌────────────┬────────────┬────────────┐
 │Investigator│ Reproducer │ Test Agent │
 │  RUNNING   │  RUNNING   │  RUNNING  │
 └────────────┴────────────┴────────────┘
        │
        ▼
Fixer Agent
        │
        ▼
Adversarial Verifier
        │
        ▼
Regression Agent
        │
        ▼
Proof Report

Clicking an agent opens its activity.

Example:

ADVERSARIAL VERIFIER

Testing fix against additional edge cases...

✓ Valid future coupon
✓ Expired coupon
✓ Disabled coupon
✓ Null expiration
● Testing timezone boundary...

This makes the agentic workflow visible rather than hiding everything behind a loading spinner.

---

16. Findings Screen

Display findings as cards.

┌────────────────────────────────────────────────────┐
│ 🔴 HIGH                           PROVEN FIXED     │
│                                                    │
│ Expired coupons can be accepted                    │
│                                                    │
│ coupon.service.ts : 84                             │
│                                                    │
│ Reproduced       ✓                                 │
│ Fix applied      ✓                                 │
│ Adversarial      6/6                               │
│ Regression       47/47                             │
│                                                    │
│ [ View Proof ]                  [ View Patch ]      │
└────────────────────────────────────────────────────┘

Filters:

All
Proven
Fixed
Rejected
Unverified

Severity filters:

Critical
High
Medium
Low

---

17. Finding Detail / Proof Screen

This is the most important screen.

Header:

Finding #03

Expired coupons can be accepted

HIGH                        PROVEN FIXED

Claim

The coupon validation path checks whether the
coupon is enabled but does not reject an expired
coupon.

Code Evidence

src/services/coupon.service.ts

81 | const coupon = await getCoupon(code)
82 |
83 | if (!coupon.enabled)
84 |    throw new InvalidCoupon()
85 |
86 | return applyDiscount(coupon)

Highlight relevant lines.

---

Reproduction

Generated Test
tests/coupon-expiry.proof.test.ts

Scenario:
Coupon expired yesterday.

Expected:
InvalidCoupon

Before Fix:
❌ FAILED

Observed:
Coupon accepted and discount applied.

---

Proposed Fix

Diff viewer:

 if (!coupon.enabled)
    throw new InvalidCoupon()

+if (coupon.expiresAt < new Date())
+   throw new ExpiredCoupon()

 return applyDiscount(coupon)

---

Verification

Original Reproduction Test
✓ PASS

Adversarial Tests
✓ expiresAt = yesterday
✓ expiresAt = now
✓ expiresAt = tomorrow
✓ disabled coupon
✓ timezone boundary
✓ null expiry

6 / 6 PASS

---

Regression

Existing Unit Tests        34/34
Integration Tests          13/13
Proof Tests                 7/7

TOTAL                       54/54

---

Final Result

Large badge:

✓ PROVEN FIXED

Supporting statement:

The issue was reproduced before the patch.

The original reproduction no longer exposes the
problem after the patch, all generated adversarial
checks passed, and the existing regression suite
remained green.

---

18. Rejected Finding UI

This feature is important because it demonstrates that ProofPR does not blindly trust its own agents.

Finding #05

Potential null pointer in UserService

Investigator:
Possible null user object.

Reproducer:
Unable to reproduce.

Evidence discovered:
Repository middleware guarantees authenticated
requests contain a populated user object.

Generated tests:
5/5 PASS

Final Status:

✕ REJECTED

Reason:
The original finding did not account for the
authentication middleware contract.

This visually demonstrates false-positive filtering.

---

19. Agent Disagreement UI

Example:

Finding #06

Possible unauthorized admin update

Agent opinions:

Security Investigator
⚠ Potential vulnerability

Requirement Agent
⚠ Admin-only operation

Context Agent
✓ Route uses auth middleware

Reproducer
✕ Unauthorized request returned HTTP 403

Then:

Evidence Resolution

Executable reproduction contradicts the
original security claim.

FINAL STATUS: REJECTED

The key principle:

Evidence > Agent Vote

---

20. Tests Screen

Test Verification

Existing Tests
47 / 47 PASS

Generated Reproduction Tests
4 / 4 PASS after fixes

Adversarial Tests
13 / 13 PASS

Regression Tests
47 / 47 PASS

Expandable table:

Test                         Type          Result

expired_coupon               Reproduction  PASS
timezone_expiration          Adversarial   PASS
disabled_expired_coupon      Adversarial   PASS
coupon_no_expiration         Edge Case     PASS
checkout_existing_flow       Regression    PASS

---

21. Proof Timeline

Another visually strong screen.

10:41:02  PR analysis started

10:41:05  Requirements extracted

10:41:09  Investigator identified Finding #03

10:41:14  Reproduction test generated

10:41:17  Test FAILED
          Bug confirmed

10:41:23  Patch generated

10:41:27  Reproduction test PASS

10:41:32  6 adversarial tests generated

10:41:38  6/6 PASS

10:41:44  Regression suite completed

10:41:45  Finding marked PROVEN FIXED

This provides an audit trail.

---

22. Final Report Screen

Header:

ProofPR Verification Report

shop-api / PR #42

Verification completed in 43 seconds.

Summary:

Potential Findings       9

Proven                    5
Rejected                  3
Unverified                1

Fixes Generated           5
Fixes Verified            5

Tests Generated          18
Tests Passed             18

Existing Tests           47/47

Then:

VERIFICATION RESULT

All reproduced critical/high-severity findings
addressed by the current candidate patch.

Buttons:

[ Export Report ]

[ View Evidence ]

[ View Proposed Changes ]

For the hackathon MVP, do not automatically merge the PR.

---

23. UI Design System

Visual Direction

ProofPR should look like a serious developer platform rather than a generic AI chatbot.

Inspiration:

- GitHub
- Linear
- Vercel
- modern observability dashboards

Theme

Dark developer-oriented interface.

Suggested palette:

Background:
"#09090B"

Cards:
"#111113"

Borders:
"#27272A"

Primary:
indigo/violet

Success:
green

Warning:
amber

Failure:
red

Text:
white / zinc

Typography

Primary:

Inter

Code:

JetBrains Mono

Components

Use:

- cards
- badges
- diff viewer
- tabs
- progress bars
- status indicators
- collapsible evidence sections
- test result tables
- agent execution timeline
- pipeline visualization
- code blocks

Avoid excessive gradients and unnecessary AI-style glowing effects.

---

24. Frontend Architecture

Recommended:

React
TypeScript
Vite
Tailwind CSS
shadcn/ui
Lucide Icons
Framer Motion
React Flow

React Flow can visualize:

Agent
 ↓
Agent
 ↓
Verification

Framer Motion should only provide subtle transitions.

---

25. Backend Architecture

Recommended:

FastAPI
Python
Pydantic
GitHub API
Subprocess/Test Runner
SQLite
WebSockets / SSE
IBM Bob workflows

High-level architecture:

                GitHub
                   │
                   ▼
            ProofPR Backend
                   │
          Context Collector
                   │
                   ▼
             Bob Orchestrator
                   │
      ┌────────────┼─────────────┐
      ▼            ▼             ▼
Investigator   Requirement   Reproducer
      │            │             │
      └────────────┼─────────────┘
                   ▼
             Evidence Engine
                   │
                   ▼
                 Fixer
                   │
                   ▼
        Adversarial Verifier
                   │
                   ▼
           Regression Runner
                   │
                   ▼
            Proof Generator
                   │
                   ▼
               React UI

---

26. Suggested Data Model

PullRequest

id
repository
pr_number
title
description
branch
base_branch
status
created_at

Finding

id
pr_id
title
description
severity
file
line
claim
status
created_by_agent

Evidence

id
finding_id
type
description
file
line
content

TestExecution

id
finding_id
test_name
test_type
command
expected_result
actual_result
status
execution_time

Patch

id
finding_id
diff
generated_by
verification_status

AgentExecution

id
agent_name
finding_id
status
started_at
completed_at
summary

---

27. Suggested API

POST /api/verify

GET /api/pr/{id}

GET /api/pr/{id}/findings

GET /api/findings/{id}

GET /api/findings/{id}/evidence

GET /api/findings/{id}/tests

GET /api/findings/{id}/patch

GET /api/pr/{id}/agents

GET /api/pr/{id}/timeline

GET /api/pr/{id}/report

WS /api/verification/{id}/stream

The WebSocket/SSE stream allows the UI to display Bob agent activity live.

---

28. MVP Scope

For hackathon completion, prioritize:

Must Have

- GitHub PR input
- PR diff extraction
- requirement/context analysis
- Investigator agent
- Reproducer agent
- Fixer agent
- Adversarial Verifier
- test execution
- regression execution
- proven/rejected statuses
- evidence screen
- live agent pr
