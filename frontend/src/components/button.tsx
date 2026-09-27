import { Link, type LinkProps } from "@tanstack/react-router";
import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "outline" | "ghost";
const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/85 border-primary",
  outline: "bg-transparent text-foreground hover:bg-accent border-border",
  ghost: "bg-transparent text-muted-foreground hover:bg-accent hover:text-foreground border-transparent",
};
const base = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50";
export function Button({ variant = "outline", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={cn(base, variants[variant], className)} {...props} />;
}
export function ButtonLink({ variant = "outline", className, children, ...props }: LinkProps & { variant?: Variant; className?: string; children: ReactNode }) {
  return <Link className={cn(base, variants[variant], className)} {...props}>{children}</Link>;
}
