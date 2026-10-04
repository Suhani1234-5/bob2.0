export class InvalidCoupon extends Error {
  constructor(code: string) {
    super(`Invalid coupon: ${code}`);
  }
}

export class ExpiredCoupon extends InvalidCoupon {}

export interface Coupon {
  code: string;
  enabled: boolean;
  discount: number;
  expiresAt: Date | null;
}

export class CouponService {
  constructor(
    private readonly coupons: Map<string, Coupon>,
    private readonly now: () => Date = () => new Date(),
  ) {}

  validate(code: string): Coupon {
    const coupon = this.coupons.get(code.toUpperCase());
    if (!coupon || !coupon.enabled) throw new InvalidCoupon(code);
    if (coupon.expiresAt !== null && coupon.expiresAt.getTime() <= this.now().getTime()) {
      throw new ExpiredCoupon(code);
    }
    return coupon;
  }

  applyCoupon(code: string, subtotal: number): number {
    const coupon = this.coupons.get(code.toUpperCase());
    if (!coupon || !coupon.enabled) throw new InvalidCoupon(code);
    return Math.max(0, subtotal - coupon.discount);
  }
}
