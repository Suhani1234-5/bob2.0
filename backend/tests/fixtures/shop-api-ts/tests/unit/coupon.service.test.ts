import { Coupon, CouponService, ExpiredCoupon, InvalidCoupon } from "../../src/coupon.service";

const NOW = new Date("2026-03-14T12:00:00Z");

function makeService(extra: Coupon[] = []): CouponService {
  const coupons: Coupon[] = [
    { code: "SAVE10", enabled: true, discount: 10, expiresAt: null },
    { code: "OFF", enabled: false, discount: 5, expiresAt: null },
    { code: "SPRING", enabled: true, discount: 15, expiresAt: new Date("2026-04-01T00:00:00Z") },
    ...extra,
  ];
  return new CouponService(new Map(coupons.map((c) => [c.code, c])), () => NOW);
}

describe("CouponService", () => {
  it("rejects unknown coupons", () => {
    expect(() => makeService().validate("NOPE")).toThrow(InvalidCoupon);
  });
  it("rejects disabled coupons at checkout", () => {
    expect(() => makeService().applyCoupon("OFF", 20)).toThrow(InvalidCoupon);
  });
  it("applies a fixed discount", () => {
    expect(makeService().applyCoupon("SAVE10", 50)).toBe(40);
  });
  it("never returns a negative total", () => {
    expect(makeService().applyCoupon("SAVE10", 4)).toBe(0);
  });
  it("is case-insensitive", () => {
    expect(makeService().validate("save10").code).toBe("SAVE10");
  });
  it("validate rejects expired coupons", () => {
    const svc = makeService([{ code: "OLD", enabled: true, discount: 5, expiresAt: new Date("2026-03-13T12:00:00Z") }]);
    expect(() => svc.validate("OLD")).toThrow(ExpiredCoupon);
  });
  it("validate accepts future coupons", () => {
    expect(makeService().validate("SPRING").code).toBe("SPRING");
  });
});
