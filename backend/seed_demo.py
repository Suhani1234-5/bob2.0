import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from datetime import datetime, timezone
import database as db

def seed():
    db.init_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Create Sample PR (#42)
    pr_id = db.insert_pull_request(
        repository="shop-api",
        pr_number=42,
        title="Add coupon expiration validation",
        description="Fixes coupon application to check validity period before applying discounts.",
        branch="feature/coupon-expiry",
        base_branch="main",
        status="completed",
    )
    print(f"Created PR record id: {pr_id}")

    # 2. Finding #03: Proven Fixed Defect
    f1_id = db.insert_findings(
        pr_id=pr_id,
        findings=[
            type("Candidate", (), {
                "title": "Expired coupons can be accepted",
                "description": "Discount validation checks enabled=true but does not compare expiresAt with current time.",
                "severity": "high",
                "file": "src/services/coupon.service.ts",
                "line": 84,
                "claim": "The coupon validation path checks whether the coupon is enabled but does not reject an expired coupon.",
            })()
        ],
    )[0]
    db.update_finding_status(f1_id, "proven_fixed")

    # Add Evidence for Finding #03
    db.insert_evidence(
        finding_id=f1_id,
        evidence_type="code",
        description="Missing expiry check before applyDiscount()",
        file="src/services/coupon.service.ts",
        line=84,
        content="if (!coupon.enabled)\n    throw new InvalidCoupon()\n\nreturn applyDiscount(coupon)",
    )

    # Add Tests for Finding #03
    db.insert_test_execution(
        finding_id=f1_id,
        test_name="tests/coupon-expiry.proof.test.ts",
        test_type="reproduction",
        command="npm test tests/coupon-expiry.proof.test.ts",
        expected_result="InvalidCoupon error thrown",
        actual_result="Passed: Coupon rejected",
        status="pass",
        execution_time=0.42,
    )
    db.insert_test_execution(
        finding_id=f1_id,
        test_name="timezone_expiration_boundary",
        test_type="adversarial",
        command="npm test tests/adversarial.test.ts",
        expected_result="InvalidCoupon error thrown on exact timestamp",
        actual_result="Passed",
        status="pass",
        execution_time=0.28,
    )

    # Add Patch for Finding #03
    db.insert_patch(
        finding_id=f1_id,
        diff="""@@ -83,3 +83,5 @@
 if (!coupon.enabled)
     throw new InvalidCoupon()
+if (coupon.expiresAt < new Date())
+    throw new ExpiredCoupon()
 return applyDiscount(coupon)""",
        generated_by="FixerAgent",
        verification_status="verified",
    )

    # 3. Finding #05: Rejected Finding
    f2_id = db.insert_findings(
        pr_id=pr_id,
        findings=[
            type("Candidate", (), {
                "title": "Potential null pointer in UserService",
                "description": "Investigator claimed user object could be null during checkout.",
                "severity": "medium",
                "file": "src/services/user.service.ts",
                "line": 42,
                "claim": "User object can be null when accessing user.id.",
            })()
        ],
    )[0]
    db.update_finding_status(f2_id, "rejected")

    db.insert_evidence(
        finding_id=f2_id,
        evidence_type="code",
        description="Auth middleware guarantees non-null session object",
        file="src/middleware/auth.ts",
        line=15,
        content="if (!req.user) return res.status(401).send();",
    )

    # 4. Agent Execution Timeline
    db.insert_agent_execution(
        agent_name="RequirementAgent",
        finding_id=None,
        status="completed",
        started_at=now,
        summary="PR requirements extracted: coupon validation and expiry enforcement.",
    )
    db.insert_agent_execution(
        agent_name="InvestigatorAgent",
        finding_id=f1_id,
        status="completed",
        started_at=now,
        summary="Discovered missing expiresAt check in coupon.service.ts:84.",
    )
    db.insert_agent_execution(
        agent_name="ReproducerAgent",
        finding_id=f1_id,
        status="completed",
        started_at=now,
        summary="Reproduction test confirmed bug: expired coupon was accepted.",
    )
    db.insert_agent_execution(
        agent_name="FixerAgent",
        finding_id=f1_id,
        status="completed",
        started_at=now,
        summary="Generated minimal patch adding expiresAt check.",
    )
    db.insert_agent_execution(
        agent_name="AdversarialVerifier",
        finding_id=f1_id,
        status="completed",
        started_at=now,
        summary="Ran 6 edge-case inputs (null expiry, timezone boundaries). All passed.",
    )

    print("Demo seed data created successfully!")

if __name__ == "__main__":
    seed()
