import { checkout } from "../../src/checkout";
import { Coupon, CouponService } from "../../src/coupon.service";

const NOW = new Date("2026-03-14T12:00:00Z");
const service = new CouponService(
  new Map<string, Coupon>([["SAVE10", { code: "SAVE10", enabled: true, discount: 10, expiresAt: null }]]),
  () => NOW,
);

describe("checkout", () => {
  it("charges the subtotal without a coupon", () => {
    expect(checkout(service, 30)).toEqual({ status: 200, total: 30 });
  });
  it("applies a coupon", () => {
    expect(checkout(service, 30, "SAVE10")).toEqual({ status: 200, total: 20 });
  });
  it("returns 400 for an unknown coupon", () => {
    expect(checkout(service, 30, "NOPE")).toEqual({ status: 400, error: "InvalidCoupon" });
  });
});
