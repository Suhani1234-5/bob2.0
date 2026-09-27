import { Check, CircleDashed, X } from "lucide-react";
import type { FindingStatus, Severity } from "@/lib/proof-data";
import { cn } from "@/lib/utils";

export function StatusBadge({ status, large = false }: { status: FindingStatus; large?: boolean }) {
  const icon = status === "REJECTED" ? <X size={large ? 17 : 12} strokeWidth={2.5} /> : status === "UNVERIFIED" ? <CircleDashed size={large ? 17 : 12} /> : <Check size={large ? 17 : 12} strokeWidth={2.5} />;
  return <span className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border font-semibold tracking-wide", large ? "px-4 py-2 text-sm" : "px-2.5 py-1 text-[10px]", status === "PROVEN FIXED" ? "border-success/30 bg-success/10 text-success" : status === "PROVEN" ? "border-info/30 bg-info/10 text-info" : status === "REJECTED" ? "border-danger/30 bg-danger/10 text-danger" : "border-warning/30 bg-warning/10 text-warning")}>{icon}{status}</span>;
}
export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={cn("inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide", severity === "critical" || severity === "high" ? "text-danger" : severity === "medium" ? "text-warning" : "text-info")}><span className="size-1.5 rounded-full bg-current" />{severity}</span>;
}
