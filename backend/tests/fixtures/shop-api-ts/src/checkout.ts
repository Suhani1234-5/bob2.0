import { CouponService, InvalidCoupon } from "./coupon.service";

export interface CheckoutResult {
  status: number;
  total?: number;
  error?: string;
}

export function checkout(service: CouponService, subtotal: number, code?: string): CheckoutResult {
  try {
    const total = code ? service.applyCoupon(code, subtotal) : subtotal;
    return { status: 200, total };
  } catch (err) {
    if (err instanceof InvalidCoupon) return { status: 400, error: err.constructor.name };
    throw err;
  }
}
