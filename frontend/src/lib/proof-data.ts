export type Severity = "critical" | "high" | "medium" | "low";
export type FindingStatus = "PROVEN FIXED" | "PROVEN" | "REJECTED" | "UNVERIFIED" | "FIX FAILED";
export type Finding = {
  id: string;
  title: string;
  severity: Severity;
  status: FindingStatus;
  file: string;
  line: number;
  claim: string;
  reproduction_test: string;
  scenario: string;
  expected: string;
  actual: string;
  before_fix_result: string;
  code_evidence: { line: number; code: string; flagged?: boolean }[];
  full_file_content?: { line: number; code: string }[];
  patch_diff: { type: "context" | "removed" | "added"; code: string; oldLine?: number; newLine?: number }[];
  adversarial_tests: { name: string; passed: boolean }[];
  regression: { unit: [number, number]; integration: [number, number]; proof: [number, number]; total: [number, number] };
  final_status: FindingStatus;
  reason?: string;
  evidence_discovered?: string;
  failing_checks?: string[];
};

const regression: Finding["regression"] = { unit: [34, 34], integration: [13, 13], proof: [7, 7], total: [54, 54] };

export const findings: Finding[] = [
  {
    id: "FND-001", title: "Expired coupons can be accepted", severity: "high", status: "PROVEN FIXED",
    file: "src/services/coupon.service.ts", line: 84,
    claim: "The coupon validation path checks whether a coupon exists and is active, but never compares its expiration time against the current time. An expired coupon can therefore still be applied to an order.",
    reproduction_test: "should reject a coupon with an expired expiresAt", scenario: "Apply SAVE20 to a cart after its expiresAt timestamp has passed.",
    expected: "CouponExpiredError is returned; no discount is applied.", actual: "Coupon was accepted and a 20% discount was applied.", before_fix_result: "FAILED",
    code_evidence: [
      { line: 80, code: "async validateCoupon(code: string) {" },
      { line: 81, code: "  const coupon = await this.repo.findByCode(code);" },
      { line: 82, code: "  if (!coupon) throw new CouponNotFoundError();" },
      { line: 83, code: "  if (!coupon.isActive) throw new CouponInactiveError();" },
      { line: 84, code: "  return coupon;", flagged: true },
      { line: 85, code: "}" },
    ],
    full_file_content: [
      { line: 1,  code: "import { Injectable } from '@nestjs/common';" },
      { line: 2,  code: "import { CouponRepository } from '../repositories/coupon.repository';" },
      { line: 3,  code: "import { CouponNotFoundError, CouponInactiveError, CouponExpiredError } from '../errors';" },
      { line: 4,  code: "" },
      { line: 5,  code: "@Injectable()" },
      { line: 6,  code: "export class CouponService {" },
      { line: 7,  code: "  constructor(private readonly repo: CouponRepository) {}" },
      { line: 8,  code: "" },
      { line: 9,  code: "  async findAll() {" },
      { line: 10, code: "    return this.repo.findAll();" },
      { line: 11, code: "  }" },
      { line: 12, code: "" },
      { line: 13, code: "  async findById(id: string) {" },
      { line: 14, code: "    return this.repo.findById(id);" },
      { line: 15, code: "  }" },
      { line: 16, code: "" },
      { line: 17, code: "  async create(dto: CreateCouponDto) {" },
      { line: 18, code: "    return this.repo.create(dto);" },
      { line: 19, code: "  }" },
      { line: 20, code: "" },
      { line: 70, code: "  // ..." },
      { line: 71, code: "" },
      { line: 72, code: "  async applyCoupon(code: string, cart: Cart) {" },
      { line: 73, code: "    const coupon = await this.validateCoupon(code);" },
      { line: 74, code: "    return this.applyDiscount(coupon, cart);" },
      { line: 75, code: "  }" },
      { line: 76, code: "" },
      { line: 77, code: "  private applyDiscount(coupon: Coupon, cart: Cart) {" },
      { line: 78, code: "    const discount = coupon.amount ?? cart.subtotal * (coupon.percent / 100);" },
      { line: 79, code: "    return Math.max(0, cart.subtotal - discount);" },
      { line: 80, code: "  }" },
      { line: 81, code: "" },
      { line: 82, code: "  async validateCoupon(code: string) {" },
      { line: 83, code: "    const coupon = await this.repo.findByCode(code);" },
      { line: 84, code: "    if (!coupon) throw new CouponNotFoundError();" },
      { line: 85, code: "    if (!coupon.isActive) throw new CouponInactiveError();" },
      { line: 86, code: "    return coupon;", flagged: true },
      { line: 87, code: "  }" },
      { line: 88, code: "}" },
    ],
    patch_diff: [
      { type: "context", code: "  if (!coupon.isActive) throw new CouponInactiveError();", oldLine: 83, newLine: 83 },
      { type: "removed", code: "  return coupon;", oldLine: 84 },
      { type: "added", code: "  if (coupon.expiresAt && coupon.expiresAt <= new Date()) {", newLine: 84 },
      { type: "added", code: "    throw new CouponExpiredError();", newLine: 85 },
      { type: "added", code: "  }", newLine: 86 },
      { type: "added", code: "  return coupon;", newLine: 87 },
    ],
    adversarial_tests: [
      { name: "expiresAt = yesterday", passed: true }, { name: "expiresAt = now", passed: true },
      { name: "expiresAt = tomorrow", passed: true }, { name: "null expiry", passed: true },
      { name: "timezone boundary", passed: true }, { name: "inactive and expired", passed: true },
    ], regression, final_status: "PROVEN FIXED",
    reason: "The issue was reproduced before the patch, then the fix passed all adversarial and regression checks.",
  },
  {
    id: "FND-002", title: "Coupon reuse bypasses per-user limit", severity: "high", status: "PROVEN FIXED",
    file: "src/services/redemption.service.ts", line: 112,
    claim: "The redemption count is checked before the transaction starts, allowing two concurrent requests to pass the per-user limit.",
    reproduction_test: "blocks concurrent coupon redemptions beyond user limit", scenario: "Submit two simultaneous redemption requests for a single-use coupon.",
    expected: "Only one redemption succeeds.", actual: "Both redemptions succeeded.", before_fix_result: "FAILED",
    code_evidence: [{ line: 110, code: "const count = await getRedemptionCount(userId, couponId);" }, { line: 111, code: "if (count >= coupon.perUserLimit) throw new LimitError();" }, { line: 112, code: "return db.transaction(() => redeem(couponId, userId));", flagged: true }],
    patch_diff: [{ type: "removed", code: "return db.transaction(() => redeem(couponId, userId));", oldLine: 112 }, { type: "added", code: "return db.transaction(() => redeemWithUserLock(couponId, userId));", newLine: 112 }],
    adversarial_tests: [{ name: "two concurrent requests", passed: true }, { name: "replayed request", passed: true }, { name: "different users", passed: true }], regression, final_status: "PROVEN FIXED", reason: "Concurrent redemption was reproduced and prevented by the transactional lock.",
  },
  {
    id: "FND-003", title: "Discount total can become negative", severity: "medium", status: "PROVEN FIXED",
    file: "src/utils/price.ts", line: 39,
    claim: "A fixed-value coupon larger than the cart subtotal can produce a negative order total.",
    reproduction_test: "clamps discount at cart subtotal", scenario: "Apply a $50 coupon to a $30 cart.", expected: "Total remains $0.00.", actual: "Total became -$20.00.", before_fix_result: "FAILED",
    code_evidence: [{ line: 38, code: "const discount = coupon.amount;" }, { line: 39, code: "return subtotal - discount;", flagged: true }],
    patch_diff: [{ type: "removed", code: "return subtotal - discount;", oldLine: 39 }, { type: "added", code: "return Math.max(0, subtotal - discount);", newLine: 39 }],
    adversarial_tests: [{ name: "discount exceeds subtotal", passed: true }, { name: "discount equals subtotal", passed: true }, { name: "zero subtotal", passed: true }], regression, final_status: "PROVEN FIXED", reason: "A negative total was reproduced and is now clamped to zero.",
  },
  {
    id: "FND-004", title: "Coupon code matching ignores casing", severity: "low", status: "PROVEN",
    file: "src/repositories/coupon.repository.ts", line: 27,
    claim: "Coupon lookup is case-sensitive, so valid lowercase input does not match an uppercase coupon code.",
    reproduction_test: "matches coupon codes case-insensitively", scenario: "Enter save20 for coupon SAVE20.", expected: "Coupon is found.", actual: "Coupon was not found.", before_fix_result: "FAILED",
    code_evidence: [{ line: 26, code: "async findByCode(code: string) {" }, { line: 27, code: "  return this.db.coupon.findUnique({ where: { code } });", flagged: true }],
    patch_diff: [], adversarial_tests: [{ name: "mixed-case input", passed: false }], regression, final_status: "PROVEN", reason: "The mismatch is reproducible; no patch has been applied yet.",
  },
  {
    id: "FND-005", title: "Null expiry crashes validation", severity: "medium", status: "REJECTED",
    file: "src/services/coupon.service.ts", line: 84,
    claim: "Coupons without an expiration date might throw when expiration is checked, blocking perpetual coupons.",
    reproduction_test: "allows coupons with null expiresAt", scenario: "Apply an active coupon whose expiresAt is null.",
    expected: "The coupon is accepted without an exception.", actual: "The coupon was accepted as expected.", before_fix_result: "UNABLE TO REPRODUCE",
    code_evidence: [{ line: 83, code: "if (!coupon.isActive) throw new CouponInactiveError();" }, { line: 84, code: "if (coupon.expiresAt && coupon.expiresAt <= new Date()) {", flagged: true }, { line: 85, code: "  throw new CouponExpiredError();" }, { line: 86, code: "}" }],
    patch_diff: [], adversarial_tests: [{ name: "null expiry", passed: true }, { name: "undefined expiry", passed: true }], regression, final_status: "REJECTED",
    evidence_discovered: "The expiration comparison is guarded by a truthiness check. A null value skips the comparison, so no exception occurs.",
    reason: "False positive — null expiry is already handled by the existing guard.",
  },
  {
    id: "FND-006", title: "Percentage discount exceeds configured cap", severity: "medium", status: "REJECTED",
    file: "src/services/discount.service.ts", line: 56,
    claim: "Percentage discounts might exceed the configured maximum discount amount.",
    reproduction_test: "enforces maximum discount cap", scenario: "Apply a 50% coupon to a high-value cart with a $25 cap.",
    expected: "Discount is limited to $25.", actual: "Discount was limited to $25.", before_fix_result: "UNABLE TO REPRODUCE",
    code_evidence: [{ line: 55, code: "const rawDiscount = subtotal * (coupon.percent / 100);" }, { line: 56, code: "return Math.min(rawDiscount, coupon.maxDiscount);", flagged: true }],
    patch_diff: [], adversarial_tests: [{ name: "large cart value", passed: true }], regression, final_status: "REJECTED",
    evidence_discovered: "The calculation already uses Math.min to enforce the configured cap.", reason: "False positive — the cap is already enforced.",
  },
  {
    id: "FND-007", title: "Timezone boundary may expire coupons early", severity: "medium", status: "UNVERIFIED",
    file: "src/utils/dates.ts", line: 18,
    claim: "A local timezone conversion may shift expiration boundaries and invalidate coupons before their intended UTC deadline.",
    reproduction_test: "honors UTC coupon expiration boundary", scenario: "Apply a coupon one minute before midnight UTC from a UTC+14 locale.",
    expected: "Coupon remains valid until the UTC deadline.", actual: "No conclusive result yet.", before_fix_result: "PENDING",
    code_evidence: [{ line: 17, code: "export function isExpired(date: string) {" }, { line: 18, code: "  return new Date(date).getTime() < Date.now();", flagged: true }],
    patch_diff: [], adversarial_tests: [{ name: "UTC+14 boundary", passed: false }, { name: "daylight saving shift", passed: false }], regression, final_status: "UNVERIFIED", reason: "The boundary case has not been reproduced or ruled out yet.",
  },
  {
    id: "FND-008", title: "Cart total recalculation skips applied coupons", severity: "high", status: "FIX FAILED",
    file: "src/services/cart.service.ts", line: 67,
    claim: "When items are added to a cart after a coupon is applied, the coupon discount is not reapplied during recalculation, leaving the cart total incorrect.",
    reproduction_test: "reapplies coupon discount after cart item addition", scenario: "Apply a 10% coupon to a cart, then add a new item. Verify the discount is recalculated.",
    expected: "Total reflects 10% off the updated subtotal.", actual: "Total only reflects 10% off the original subtotal; new item is full price.", before_fix_result: "FAILED",
    code_evidence: [
      { line: 64, code: "async recalculateTotal(cartId: string) {" },
      { line: 65, code: "  const cart = await this.repo.findById(cartId);" },
      { line: 66, code: "  const subtotal = cart.items.reduce((s, i) => s + i.price, 0);" },
      { line: 67, code: "  cart.total = subtotal;", flagged: true },
      { line: 68, code: "  return this.repo.save(cart);" },
      { line: 69, code: "}" },
    ],
    patch_diff: [
      { type: "context", code: "  const subtotal = cart.items.reduce((s, i) => s + i.price, 0);", oldLine: 66, newLine: 66 },
      { type: "removed", code: "  cart.total = subtotal;", oldLine: 67 },
      { type: "added", code: "  const discount = cart.coupon ? this.computeDiscount(cart.coupon, subtotal) : 0;", newLine: 67 },
      { type: "added", code: "  cart.total = Math.max(0, subtotal - discount);", newLine: 68 },
    ],
    adversarial_tests: [
      { name: "add item after coupon applied", passed: false },
      { name: "remove item after coupon applied", passed: false },
      { name: "coupon removed after item add", passed: true },
      { name: "multiple items added sequentially", passed: false },
      { name: "free shipping coupon unaffected", passed: true },
    ],
    regression: { unit: [34, 34], integration: [11, 13], proof: [5, 7], total: [50, 54] },
    final_status: "FIX FAILED",
    reason: "The proposed patch does not correctly handle sequential item mutations; three adversarial checks still fail after the patch was applied.",
    failing_checks: [
      "add item after coupon applied",
      "remove item after coupon applied",
      "multiple items added sequentially",
    ],
  },
];

export const findingById = (id: string) => findings.find((finding) => finding.id === id);
