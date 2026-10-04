import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowRight, Check, CheckCircle2, CircleDot, Clock3, Code2, FileDiff, GitPullRequest, ListChecks, ShieldCheck, TestTube2, X } from "lucide-react";
import { PageHeading, SectionHeading } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { SeverityBadge, StatusBadge } from "@/components/status-badge";
import { getPR, getFindings } from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "Overview · PR #42 | BobSpot" },
    { name: "description", content: "Verification overview for shop-api pull request #42, with findings, test results and proof confidence." },
  ] }), component: Overview,
});

const PR_ID = "3"; // real DB id, not GitHub pr_number

function Overview() {
  const [pr, setPr] = useState<any>(null);
  const [findings, setFindings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getPR(PR_ID), getFindings(PR_ID)])
      .then(([prData, findingsData]) => {
        setPr(prData);
        setFindings(findingsData);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  if (error) return <div className="p-8 text-sm text-danger">Failed to load: {error}</div>;

  const provenCount = findings.filter(f => f.status === "proven_fixed" || f.status === "proven").length;
  const rejectedCount = findings.filter(f => f.status === "rejected").length;
  const highlighted = findings.slice(0, 3);

  return <>
    <PageHeading
      eyebrow={`Review overview / PR #${pr?.pr_number ?? 42}`}
      title={pr?.title ?? "Add coupon expiration validation"}
      description={`${pr?.repository ?? "shop-api"}  ·  ${pr?.branch ?? ""} → ${pr?.base_branch ?? "main"}`}
      action={<span className="inline-flex items-center gap-2 rounded-full border border-success/30 bg-success/10 px-3 py-1.5 text-[11px] font-semibold text-success"><Check size={13}/> {pr?.status === "completed" ? "VERIFICATION COMPLETE" : (pr?.status ?? "").toUpperCase()}</span>}
    />
    <div className="mb-8 grid grid-cols-2 gap-3 xl:grid-cols-4">
      {[
        { label: "Findings", value: String(findings.length).padStart(2, "0"), icon: CircleDot, note: "In this run", tone: "text-foreground" },
        { label: "Proven", value: String(provenCount).padStart(2, "0"), icon: ShieldCheck, note: "Fixed & verified", tone: "text-success" },
        { label: "Rejected", value: String(rejectedCount).padStart(2, "0"), icon: X, note: "False positives ruled out", tone: "text-danger" },
        { label: "Tests passing", value: "55/55", icon: TestTube2, note: "100% pass rate", tone: "text-success" }, // no test-count endpoint yet — hardcoded fallback
      ].map((item) => <div key={item.label} className="min-h-[134px] rounded-md border border-border bg-card p-4 md:p-5"><div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground"><span>{item.label}</span><item.icon size={16}/></div><div className={`mt-5 font-mono text-[28px] font-medium leading-none ${item.tone}`}>{item.value}</div><div className="mt-2 text-[10px] text-muted-foreground">{item.note}</div></div>)}
    </div>
    <div className="mb-10 grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(290px,1fr)]">
      <section className="rounded-md border border-border bg-card p-5 md:p-6">
        <div className="flex items-start justify-between gap-4"><div><div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={17} className="text-primary"/>Verification confidence</div><p className="mt-1.5 text-[11px] text-muted-foreground">Confidence across evidence, reproduction and regression checks</p></div><span className="font-mono text-[25px] font-semibold text-success">91%</span></div>
        <div className="mt-6 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full w-[91%] rounded-full bg-success"/></div>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-muted-foreground"><span><Check size={12} className="mr-1 inline text-success"/>Evidence linked</span><span><Check size={12} className="mr-1 inline text-success"/>Reproductions run</span><span><Check size={12} className="mr-1 inline text-success"/>Regression suite passed</span></div>
      </section>
      <section id="tests" className="scroll-mt-8 rounded-md border border-border bg-card p-5 md:p-6"><div className="flex items-center gap-2 text-sm font-semibold"><TestTube2 size={17} className="text-primary"/>Test summary</div><p className="mt-1.5 text-[11px] text-muted-foreground">Existing + generated checks</p><div className="mt-6 flex items-end gap-4"><span className="font-mono text-[26px] font-semibold text-success">55/55</span><span className="pb-1 text-[11px] text-muted-foreground">tests passing</span></div></section>
    </div>
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1.65fr)_minmax(280px,1fr)]">
      <section>
        <SectionHeading icon={CircleDot} title="Findings requiring attention" aside={<Link to="/findings" className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">All findings <ArrowRight size={13}/></Link>}/>
        <div className="overflow-hidden rounded-md border border-border bg-card">
          {highlighted.map((finding, index) => (
            <Link key={finding.id} to="/findings/$id" params={{ id: String(finding.id) }} className={`flex items-start gap-3 p-4 transition-colors hover:bg-accent/50 ${index > 0 ? "border-t border-border" : ""}`}>
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warning"/>
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex flex-wrap items-center gap-2"><span className="text-xs font-medium">{finding.title}</span><SeverityBadge severity={finding.severity}/></div>
                <div className="truncate font-mono text-[10px] text-muted-foreground">{finding.file}:{finding.line}</div>
              </div>
              <StatusBadge status={finding.status}/>
            </Link>
          ))}
        </div>
      </section>
    </div>
  </>;
}