import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Check, CheckCircle2, CircleDot, Clock3, Code2, FileDiff, GitPullRequest, ListChecks, ShieldCheck, TestTube2, X } from "lucide-react";
import { PageHeading, SectionHeading } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { SeverityBadge, StatusBadge } from "@/components/status-badge";
import { findings } from "@/lib/proof-data";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "Overview · PR #42 | BobSpot" },
    { name: "description", content: "Verification overview for shop-api pull request #42, with findings, test results and proof confidence." },
    { property: "og:title", content: "PR #42 Verification Overview | BobSpot" },
    { property: "og:description", content: "Explore verified findings, test results and proof confidence for shop-api pull request #42." },
    { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary" },
  ] }), component: Overview,
});

function Overview() {
  const highlighted = findings.filter((finding) => ["FND-001", "FND-005", "FND-007"].includes(finding.id));
  return <>
    <PageHeading eyebrow="Review overview / PR #42" title="Add coupon expiration validation" description="shop-api  ·  6 files changed  ·  +143 −27" action={<span className="inline-flex items-center gap-2 rounded-full border border-success/30 bg-success/10 px-3 py-1.5 text-[11px] font-semibold text-success"><Check size={13}/> VERIFICATION COMPLETE</span>}/>
    <div className="mb-8 grid grid-cols-2 gap-3 xl:grid-cols-4">
      {[
        { label: "Findings", value: "07", icon: CircleDot, note: "Across 6 changed files", tone: "text-foreground" },
        { label: "Proven", value: "04", icon: ShieldCheck, note: "3 fixed · 1 open", tone: "text-success" },
        { label: "Rejected", value: "02", icon: X, note: "False positives ruled out", tone: "text-danger" },
        { label: "Tests passing", value: "55/55", icon: TestTube2, note: "100% pass rate", tone: "text-success" },
      ].map((item) => <div key={item.label} className="min-h-[134px] rounded-md border border-border bg-card p-4 md:p-5"><div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground"><span>{item.label}</span><item.icon size={16}/></div><div className={`mt-5 font-mono text-[28px] font-medium leading-none ${item.tone}`}>{item.value}</div><div className="mt-2 text-[10px] text-muted-foreground">{item.note}</div></div>)}
    </div>
    <div className="mb-10 grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(290px,1fr)]">
      <section className="rounded-md border border-border bg-card p-5 md:p-6">
        <div className="flex items-start justify-between gap-4"><div><div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={17} className="text-primary"/>Verification confidence</div><p className="mt-1.5 text-[11px] text-muted-foreground">Confidence across evidence, reproduction and regression checks</p></div><span className="font-mono text-[25px] font-semibold text-success">91%</span></div>
        <div className="mt-6 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label="Verification confidence" aria-valuenow={91} aria-valuemin={0} aria-valuemax={100}><div className="h-full w-[91%] rounded-full bg-success"/></div>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-muted-foreground"><span><Check size={12} className="mr-1 inline text-success"/>Evidence linked</span><span><Check size={12} className="mr-1 inline text-success"/>Reproductions run</span><span><Check size={12} className="mr-1 inline text-success"/>Regression suite passed</span></div>
      </section>
      <section id="tests" className="scroll-mt-8 rounded-md border border-border bg-card p-5 md:p-6"><div className="flex items-center gap-2 text-sm font-semibold"><TestTube2 size={17} className="text-primary"/>Test summary</div><p className="mt-1.5 text-[11px] text-muted-foreground">47 existing · 8 generated · 55 passed</p><div className="mt-6 flex items-end gap-4"><span className="font-mono text-[26px] font-semibold text-success">55/55</span><span className="pb-1 text-[11px] text-muted-foreground">tests passing</span></div><div className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted"><div className="h-full w-[85.45%] bg-primary"/><div className="h-full flex-1 bg-success"/></div><div className="mt-3 flex gap-5 text-[10px] text-muted-foreground"><span><span className="mr-1.5 inline-block size-1.5 rounded-full bg-primary"/>Existing</span><span><span className="mr-1.5 inline-block size-1.5 rounded-full bg-success"/>Generated</span></div></section>
    </div>
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1.65fr)_minmax(280px,1fr)]">
      <section><SectionHeading icon={CircleDot} title="Findings requiring attention" aside={<Link to="/findings" className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">All findings <ArrowRight size={13}/></Link>}/><div className="overflow-hidden rounded-md border border-border bg-card">{highlighted.map((finding, index) => <Link key={finding.id} to="/findings/$id" params={{ id: finding.id }} className={`flex items-start gap-3 p-4 transition-colors hover:bg-accent/50 ${index > 0 ? "border-t border-border" : ""}`}><span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warning"/><div className="min-w-0 flex-1"><div className="mb-1.5 flex flex-wrap items-center gap-2"><span className="text-xs font-medium">{finding.title}</span><SeverityBadge severity={finding.severity}/></div><div className="truncate font-mono text-[10px] text-muted-foreground">{finding.file}:{finding.line}</div></div><StatusBadge status={finding.status}/></Link>)}</div></section>
      <section id="agents" className="scroll-mt-8"><SectionHeading icon={Code2} title="Verification pipeline"/><div className="rounded-md border border-border bg-card px-5 py-2">{[
        ["01", "Investigator", "Claims evaluated", CheckCircle2], ["02", "Reproducer", "Tests generated & run", CheckCircle2], ["03", "Fixer", "Patches validated", CheckCircle2], ["04", "Adversary", "Edge cases challenged", CheckCircle2], ["05", "Regression", "Full suite passed", CheckCircle2],
      ].map(([number, name, detail, Icon], index) => <div key={String(number)} className={`flex items-center gap-3 py-3.5 ${index > 0 ? "border-t border-border" : ""}`}><span className="font-mono text-[10px] text-muted-foreground">{String(number)}</span><div className="flex-1"><div className="text-[11px] font-medium">{String(name)}</div><div className="mt-0.5 text-[10px] text-muted-foreground">{String(detail)}</div></div><CheckCircle2 size={15} className="text-success"/></div>)}</div></section>
    </div>
    <div className="mt-9 grid gap-8 xl:grid-cols-2"><section id="changes" className="scroll-mt-8"><SectionHeading icon={FileDiff} title="Changes"/><div className="rounded-md border border-border bg-card p-5"><div className="flex items-center justify-between gap-4"><div><div className="text-xs font-medium">Coupon validation patch</div><div className="mt-1 font-mono text-[10px] text-muted-foreground">src/services/coupon.service.ts</div></div><span className="font-mono text-[11px] text-success">+143 <span className="text-danger">−27</span></span></div><ButtonLink to="/findings/$id" params={{ id: "FND-001" }} className="mt-4">Inspect patch <ArrowRight size={13}/></ButtonLink></div></section><section id="report" className="scroll-mt-8"><SectionHeading icon={ListChecks} title="Review report"/><div className="rounded-md border border-border bg-card p-5"><p className="text-xs leading-6 text-muted-foreground">Four claims were proven, two were rejected as false positives, and one remains unverified. All 55 tests passed.</p><ButtonLink to="/findings" className="mt-4">Review findings <ArrowRight size={13}/></ButtonLink></div></section></div>
  </>;
}
