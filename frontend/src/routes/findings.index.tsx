import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleDot, FileDiff, ListFilter, Search, ShieldCheck, TestTube2 } from "lucide-react";
import { PageHeading } from "@/components/app-shell";
import { Button, ButtonLink } from "@/components/button";
import { SeverityBadge, StatusBadge } from "@/components/status-badge";
import { findings, type FindingStatus, type Severity } from "@/lib/proof-data";

export const Route = createFileRoute("/findings/")({ head: () => ({ meta: [
  { title: "Findings · PR #42 | BobSpot" },
  { name: "description", content: "Filter and inspect the AI-verified findings for shop-api pull request #42." },
  { property: "og:title", content: "Verified Findings | BobSpot" },
  { property: "og:description", content: "Inspect proven, fixed, rejected and unverified findings from shop-api pull request #42." },
  { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary" },
] }), component: FindingsPage });

type Filter = "All" | "Proven" | "Fixed" | "Rejected" | "Unverified" | "Fix Failed";
const filters: Filter[] = ["All", "Proven", "Fixed", "Rejected", "Unverified", "Fix Failed"];

function matchesFilter(status: FindingStatus, filter: Filter): boolean {
  if (filter === "All") return true;
  if (filter === "Proven") return status === "PROVEN";
  if (filter === "Fixed") return status === "PROVEN FIXED";
  if (filter === "Rejected") return status === "REJECTED";
  if (filter === "Unverified") return status === "UNVERIFIED";
  if (filter === "Fix Failed") return status === "FIX FAILED";
  return false;
}

function FindingsPage() {
  const [status, setStatus] = useState<Filter>("All");
  const [severity, setSeverity] = useState<"All severities" | Severity>("All severities");
  const [query, setQuery] = useState("");
  const visible = findings.filter((finding) => {
    return (
      matchesFilter(finding.status, status) &&
      (severity === "All severities" || severity === finding.severity) &&
      `${finding.title} ${finding.file} ${finding.id}`.toLowerCase().includes(query.toLowerCase())
    );
  });
  return <>
    <PageHeading
      eyebrow="Review / Findings"
      title="Findings"
      description="Every claim, tested against code and evidence. Nothing taken on faith."
      action={<span className="rounded-md border border-border bg-card px-3 py-2 font-mono text-[11px] text-muted-foreground">{findings.length} total findings</span>}
    />
    <div className="mb-5 flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
      <div className="flex flex-wrap gap-1 rounded-md border border-border bg-card p-1" role="group" aria-label="Filter by status">
        {filters.map((filter) => (
          <Button key={filter} variant={status === filter ? "primary" : "ghost"} onClick={() => setStatus(filter)} aria-pressed={status === filter} className="min-h-8 border-0 px-3 text-[11px]">
            {filter}
          </Button>
        ))}
      </div>
      <div className="flex gap-2">
        <label className="relative min-w-0 flex-1 lg:w-52">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"/>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search findings..." aria-label="Search findings" className="h-9 w-full rounded-md border border-border bg-card pl-9 pr-3 text-xs outline-none placeholder:text-muted-foreground focus:border-primary"/>
        </label>
        <label className="relative flex shrink-0 items-center">
          <ListFilter size={14} className="pointer-events-none absolute left-3 text-muted-foreground"/>
          <select value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)} aria-label="Filter by severity" className="h-9 appearance-none rounded-md border border-border bg-card pl-9 pr-8 text-[11px] text-foreground outline-none focus:border-primary">
            <option>All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <ChevronDown size={13} className="pointer-events-none absolute right-2.5 text-muted-foreground"/>
        </label>
      </div>
    </div>
    <div className="mb-4 flex items-center justify-between border-b border-border pb-3 text-[11px] text-muted-foreground">
      <span>Showing <strong className="font-semibold text-foreground">{visible.length}</strong> of {findings.length} findings</span>
      <span className="hidden font-mono sm:inline">PR #42 / shop-api</span>
    </div>
    <div className="space-y-3">
      {visible.map((finding) => (
        <article key={finding.id} className="rounded-md border border-border bg-card p-4 transition-colors hover:border-input md:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <SeverityBadge severity={finding.severity}/>
                <span className="font-mono text-[10px] text-muted-foreground">{finding.id}</span>
              </div>
              <Link to="/findings/$id" params={{ id: finding.id }} className="mt-2 block text-sm font-semibold hover:text-primary md:text-[15px]">{finding.title}</Link>
              <p className="mt-1.5 break-all font-mono text-[10px] text-muted-foreground">{finding.file} : {finding.line}</p>
            </div>
            <StatusBadge status={finding.status}/>
          </div>
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-4 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className={finding.status === "UNVERIFIED" ? "text-warning" : "text-success"}>
                {finding.status === "UNVERIFIED" ? "○" : "✓"}
              </span>
              {finding.status === "REJECTED" ? "Not reproduced" : finding.status === "UNVERIFIED" ? "Reproduction pending" : "Reproduced"}
            </span>
            <span className="flex items-center gap-1.5">
              <span className={finding.patch_diff.length ? "text-success" : "text-muted-foreground"}>
                {finding.patch_diff.length ? "✓" : "—"}
              </span>
              {finding.patch_diff.length ? "Fix applied" : "No patch"}
            </span>
            <span>Adversarial <strong className="font-mono font-medium text-foreground">{finding.adversarial_tests.filter((t) => t.passed).length}/{finding.adversarial_tests.length}</strong></span>
            <span>Regression <strong className="font-mono font-medium text-foreground">{finding.regression.total[0]}/{finding.regression.total[1]}</strong></span>
            {finding.status === "FIX FAILED" && (
              <span className="flex items-center gap-1 text-danger">
                ⚠ Developer review required
              </span>
            )}
          </div>
          <div className="mt-4 flex items-center gap-2">
            <ButtonLink to="/findings/$id" params={{ id: finding.id }} variant="primary">View proof <ArrowRight size={13}/></ButtonLink>
            {finding.patch_diff.length > 0 && (
              <ButtonLink to="/findings/$id" params={{ id: finding.id }} hash="patch">View patch <FileDiff size={13}/></ButtonLink>
            )}
          </div>
        </article>
      ))}
    </div>
  </>;
}
