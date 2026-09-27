import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronRight, CircleAlert,
  ClipboardCheck, Code2, FileDiff, FlaskConical, GitCompareArrows,
  Maximize2, Minimize2, ShieldCheck, Sparkles, TestTube2,
  TriangleAlert, X,
} from "lucide-react";
import { SectionHeading } from "@/components/app-shell";
import { Button, ButtonLink } from "@/components/button";
import { SeverityBadge, StatusBadge } from "@/components/status-badge";
import { findingById, findings, type Finding } from "@/lib/proof-data";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/findings/$id")({
  loader: ({ params }) => {
    const finding = findingById(params.id);
    if (!finding) throw notFound();
    return finding;
  },
  head: ({ loaderData }) => ({ meta: [
    { title: loaderData ? `${loaderData.title} · Proof | BobSpot` : "Finding not found | BobSpot" },
    { name: "description", content: loaderData ? `Review the claim, code evidence, reproduction, patch and verification for ${loaderData.title}.` : "This BobSpot finding could not be found." },
    { property: "og:title", content: loaderData ? `${loaderData.title} | BobSpot` : "Finding not found | BobSpot" },
    { property: "og:description", content: loaderData ? `Inspect the proof trail and final ${loaderData.final_status.toLowerCase()} status for ${loaderData.title}.` : "This BobSpot finding could not be found." },
    { property: "og:type", content: "article" }, { name: "twitter:card", content: "summary" },
  ] }),
  notFoundComponent: () => (
    <div className="py-20 text-center">
      <h1 className="text-2xl font-semibold">Finding not found</h1>
      <ButtonLink to="/findings" className="mt-5">Back to findings</ButtonLink>
    </div>
  ),
  component: FindingDetail,
});

// ─── Code Evidence with full-file toggle ──────────────────────────────────────
function CodeEvidence({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false);
  const flaggedRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to flagged line when expanded
  useEffect(() => {
    if (expanded && flaggedRef.current) {
      flaggedRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [expanded]);

  const rows = expanded && finding.full_file_content
    ? finding.full_file_content
    : finding.code_evidence;

  const hasFullFile = Boolean(finding.full_file_content?.length);

  return (
    <div className="overflow-x-auto rounded-md border border-code-border bg-code">
      <div className="flex min-w-max items-center justify-between border-b border-code-border px-4 py-2.5">
        <span className="font-mono text-[10px] text-muted-foreground">{finding.file}</span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-muted-foreground">TypeScript</span>
          {hasFullFile && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded border border-code-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground transition-colors hover:border-border hover:text-foreground"
              aria-label={expanded ? "Collapse to snippet" : "Expand full file"}
            >
              {expanded ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
              {expanded ? "Snippet view" : "Full file view"}
            </button>
          )}
        </div>
      </div>
      <div className={cn("min-w-max py-3 font-mono text-[11px] leading-7 md:text-xs", expanded && "max-h-[480px] overflow-y-auto")}>
        {rows.map((row) => {
          const isFlagged = Boolean((row as { flagged?: boolean }).flagged);
          return (
            <div
              key={`${row.line}-${row.code}`}
              ref={isFlagged ? flaggedRef : undefined}
              className={cn("flex pr-6", isFlagged && "border-l-2 border-danger bg-highlight-red")}
            >
              <span className="w-14 shrink-0 select-none pr-5 text-right text-muted-foreground/60">{row.line}</span>
              <span className={cn("whitespace-pre", isFlagged ? "text-danger" : "text-foreground/80")}>{row.code}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Patch diff ───────────────────────────────────────────────────────────────
function PatchDiff({ finding }: { finding: Finding }) {
  return (
    <div className="overflow-x-auto rounded-md border border-code-border bg-code">
      <div className="flex min-w-max items-center justify-between border-b border-code-border px-4 py-2.5">
        <span className="font-mono text-[10px] text-muted-foreground">{finding.file}</span>
        <span className="font-mono text-[10px] text-success">
          +{finding.patch_diff.filter((r) => r.type === "added").length}{" "}
          <span className="text-danger">−{finding.patch_diff.filter((r) => r.type === "removed").length}</span>
        </span>
      </div>
      <div className="min-w-max py-3 font-mono text-[11px] leading-7 md:text-xs">
        {finding.patch_diff.map((row, i) => (
          <div key={i} className={cn(
            "flex pr-6",
            row.type === "removed" && "bg-highlight-red text-danger",
            row.type === "added"   && "bg-highlight-green text-success",
            row.type === "context" && "text-foreground/80",
          )}>
            <span className="w-10 shrink-0 select-none pr-2 text-right text-muted-foreground/50">{row.oldLine ?? ""}</span>
            <span className="w-10 shrink-0 select-none pr-2 text-right text-muted-foreground/50">{row.newLine ?? ""}</span>
            <span className="w-5 shrink-0 select-none">{row.type === "removed" ? "−" : row.type === "added" ? "+" : " "}</span>
            <span className="whitespace-pre">{row.code}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Add Test Case form ───────────────────────────────────────────────────────
type AdversarialTest = { name: string; passed: boolean };
type TestFormState = { scenario: string; expected: string; actual: string };

const BOB_SAMPLE: TestFormState = {
  scenario: "Apply coupon with expiresAt exactly equal to current timestamp",
  expected: "Request rejected",
  actual: "Request rejected",
};

function AddTestCaseSection({
  tests,
  onAdd,
}: {
  tests: AdversarialTest[];
  onAdd: (t: AdversarialTest) => void;
}) {
  const [form, setForm] = useState<TestFormState>({ scenario: "", expected: "", actual: "" });
  const [saved, setSaved] = useState(false);

  function handleGenerate() {
    setForm(BOB_SAMPLE);
    setSaved(false);
  }

  function handleSave() {
    if (!form.scenario.trim()) return;
    const passed = form.expected.trim().toLowerCase() === form.actual.trim().toLowerCase();
    onAdd({ name: form.scenario.trim(), passed });
    setForm({ scenario: "", expected: "", actual: "" });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  const field = "h-9 w-full rounded-md border border-border bg-soft px-3 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary transition-colors";

  return (
    <section>
      <SectionHeading icon={ClipboardCheck} title="Add test case" />
      <div className="rounded-md border border-border bg-card p-5">
        <p className="mb-4 text-[11px] text-muted-foreground">
          Describe a new adversarial scenario to add to this finding's verification checks.
        </p>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Scenario description
            </label>
            <input
              value={form.scenario}
              onChange={(e) => setForm((f) => ({ ...f, scenario: e.target.value }))}
              placeholder="e.g. Apply expired coupon at exact boundary timestamp"
              className={field}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Expected result
              </label>
              <input
                value={form.expected}
                onChange={(e) => setForm((f) => ({ ...f, expected: e.target.value }))}
                placeholder="e.g. Request rejected"
                className={field}
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Actual result
              </label>
              <input
                value={form.actual}
                onChange={(e) => setForm((f) => ({ ...f, actual: e.target.value }))}
                placeholder="e.g. Request rejected"
                className={field}
              />
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={handleSave} disabled={!form.scenario.trim()}>
            <Check size={13} /> Save test case
          </Button>
          <Button
            variant="outline"
            onClick={handleGenerate}
            className="gap-1.5"
            title="Inserts a placeholder AI-generated test case"
          >
            <Sparkles size={13} className="text-primary" /> Generate with Bob
          </Button>
          {saved && (
            <span className="flex items-center gap-1 text-[11px] text-success">
              <CheckCircle2 size={13} /> Test case added
            </span>
          )}
        </div>

        {tests.length > 0 && (
          <div className="mt-5 border-t border-border pt-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              All adversarial checks ({tests.length})
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {tests.map((test) => (
                <div key={test.name} className="flex min-h-11 items-center gap-2.5 rounded-md border border-border bg-soft px-3.5 py-2.5">
                  <span className={test.passed ? "text-success" : "text-warning"}>
                    {test.passed ? <Check size={14} /> : <CircleAlert size={14} />}
                  </span>
                  <span className="font-mono text-[11px] text-foreground/85">{test.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// ─── FIX FAILED banner ────────────────────────────────────────────────────────
function FixFailedBanner({ failingChecks }: { failingChecks?: string[] }) {
  return (
    <div className="mb-8 rounded-md border border-danger/40 bg-danger/8 px-5 py-4">
      <div className="flex items-start gap-3">
        <TriangleAlert size={17} className="mt-0.5 shrink-0 text-danger" />
        <div className="min-w-0">
          <div className="text-sm font-semibold text-danger">
            Automated fix did not pass verification — requires developer review
          </div>
          <p className="mt-1 text-[11px] text-danger/80">
            The proposed patch was applied but one or more adversarial or regression checks still
            fail. Manual intervention is needed before this finding can be closed.
          </p>
          {failingChecks && failingChecks.length > 0 && (
            <div className="mt-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-danger/70">
                Failing checks
              </div>
              <ul className="space-y-1">
                {failingChecks.map((check) => (
                  <li key={check} className="flex items-center gap-2 font-mono text-[11px] text-danger/90">
                    <X size={11} className="shrink-0" />{check}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main detail component ────────────────────────────────────────────────────
function FindingDetail() {
  const finding = Route.useLoaderData();
  const [tests, setTests] = useState<AdversarialTest[]>(finding.adversarial_tests);

  const isRejected   = finding.status === "REJECTED";
  const isUnverified = finding.status === "UNVERIFIED";
  const isFixFailed  = finding.status === "FIX FAILED";

  const passed = tests.filter((t) => t.passed).length;
  const currentIndex = findings.findIndex((item) => item.id === finding.id);
  const next = findings[(currentIndex + 1) % findings.length] ?? finding;

  // Section numbering: 01=Claim, 02=Code evidence; optional sections consume further numbers
  // Build the ordered list of optional sections so each gets a stable, predictable number
  const optionalSections = [
    isRejected,                      // Evidence discovered
    finding.patch_diff.length > 0,   // Proposed fix
    !isRejected,                      // Adversarial verification
    true,                             // Regression (always)
  ];
  let _sectionCounter = 2;
  const sectionNumbers = optionalSections.map((active) => {
    _sectionCounter++;
    return active ? String(_sectionCounter).padStart(2, "0") : "";
  });
  // Index helpers
  const evidenceNum    = sectionNumbers[0] ?? "04";
  const patchNum       = sectionNumbers[1] ?? "04";
  const adversarialNum = sectionNumbers[2] ?? "05";
  const regressionNum  = sectionNumbers[3] ?? "06";

  return (
    <div className="mx-auto max-w-[1080px]">
      {/* Breadcrumb */}
      <div className="mb-7 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <Link to="/findings" className="flex items-center gap-1.5 hover:text-foreground">
          <ArrowLeft size={13}/> Findings
        </Link>
        <ChevronRight size={12}/>
        <span className="font-mono text-foreground">{finding.id}</span>
      </div>

      {/* Title row */}
      <div className="mb-8 border-b border-border pb-8">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SeverityBadge severity={finding.severity}/>
          <span className="text-muted-foreground">·</span>
          <span className="font-mono text-[11px] text-muted-foreground">{finding.file}:{finding.line}</span>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <h1 className="text-[26px] font-semibold leading-tight md:text-[34px]">{finding.title}</h1>
            <p className="mt-3 text-xs text-muted-foreground">
              Verified against <span className="font-medium text-foreground">shop-api</span> · Pull request #42
            </p>
          </div>
          <StatusBadge status={finding.final_status} large/>
        </div>
      </div>

      {/* FIX FAILED banner — shown just below the title */}
      {isFixFailed && <FixFailedBanner failingChecks={finding.failing_checks ?? []} />}
      
      {/* Proof trail */}
      <div id="proof-trail" className="scroll-mt-8">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex size-7 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-primary">
            <ShieldCheck size={15}/>
          </div>
          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Proof trail</span>
          <div className="h-px flex-1 bg-border"/>
        </div>

        <div className="grid gap-x-8 gap-y-8 xl:grid-cols-[minmax(0,1fr)_260px]">
          <div className="min-w-0 space-y-9">

            {/* 01 / Claim */}
            <section>
              <SectionHeading icon={CircleAlert} title="01 / Claim"/>
              <div className="rounded-md border border-border bg-card p-5">
                <p className="text-[13px] leading-7 text-foreground/85">{finding.claim}</p>
              </div>
            </section>

            {/* 02 / Code evidence — with full file toggle */}
            <section>
              <SectionHeading
                icon={Code2}
                title="02 / Code evidence"
                aside={<span className="font-mono text-[10px] text-muted-foreground">LINE {finding.line}</span>}
              />
              <CodeEvidence finding={finding}/>
              <p className="mt-2.5 text-[11px] text-muted-foreground">
                Highlighted line was identified as the relevant code path.
                {finding.full_file_content && (
                  <> Toggle "Full file view" (top-right of the panel) to see surrounding context.</>
                )}
              </p>
            </section>

            {/* 03 / Reproduction */}
            <section>
              <SectionHeading
                icon={FlaskConical}
                title="03 / Reproduction"
                aside={
                  <span className={cn(
                    "rounded border px-2 py-1 font-mono text-[10px] font-semibold",
                    isRejected  ? "border-danger/30 bg-danger/10 text-danger" :
                    isUnverified ? "border-warning/30 bg-warning/10 text-warning" :
                                   "border-danger/30 bg-danger/10 text-danger",
                  )}>
                    {isRejected ? "UNABLE TO REPRODUCE" : isUnverified ? "PENDING" : "BEFORE FIX: FAILED"}
                  </span>
                }
              />
              <div className="overflow-hidden rounded-md border border-border bg-card">
                <div className="border-b border-border bg-soft px-5 py-3 font-mono text-[11px] text-foreground">
                  {finding.reproduction_test}
                </div>
                <div className="space-y-4 p-5">
                  <div>
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Scenario</div>
                    <p className="text-xs leading-6 text-foreground/85">{finding.scenario}</p>
                  </div>
                  <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
                    <div>
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Expected</div>
                      <p className="text-xs leading-6 text-success">{finding.expected}</p>
                    </div>
                    <div>
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Actual</div>
                      <p className={cn("text-xs leading-6", isRejected ? "text-success" : isUnverified ? "text-warning" : "text-danger")}>
                        {finding.actual}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Evidence discovered (rejected only) */}
            {isRejected && (
              <section>
                <SectionHeading icon={ShieldCheck} title={`${evidenceNum} / Evidence discovered`}/>
                <div className="rounded-md border border-danger/20 bg-danger/5 p-5">
                  <p className="text-xs leading-7 text-foreground/85">{finding.evidence_discovered}</p>
                </div>
              </section>
            )}

            {/* Proposed fix */}
            {finding.patch_diff.length > 0 && (
              <section id="patch" className="scroll-mt-8">
                <SectionHeading
                  icon={FileDiff}
                  title={`${patchNum} / Proposed fix`}
                  aside={
                    <span className={cn("text-[10px] font-semibold", isFixFailed ? "text-danger" : "text-success")}>
                      {isFixFailed ? "PATCH FAILED VERIFICATION" : "PATCH APPLIED"}
                    </span>
                  }
                />
                <PatchDiff finding={finding}/>
              </section>
            )}

            {/* Adversarial verification */}
            {!isRejected && (
              <section>
                <SectionHeading
                  icon={GitCompareArrows}
                  title={`${adversarialNum} / Adversarial verification`}
                  aside={
                    <span className={cn(
                      "font-mono text-[11px] font-semibold",
                      passed === tests.length ? "text-success" : "text-danger",
                    )}>
                      {passed}/{tests.length} passed
                    </span>
                  }
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  {tests.map((test) => (
                    <div key={test.name} className="flex min-h-11 items-center gap-2.5 rounded-md border border-border bg-card px-3.5 py-2.5">
                      <span className={test.passed ? "text-success" : isFixFailed ? "text-danger" : "text-warning"}>
                        {test.passed ? <Check size={14}/> : <CircleAlert size={14}/>}
                      </span>
                      <span className="font-mono text-[11px] text-foreground/85">{test.name}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Regression */}
            <section>
              <SectionHeading icon={TestTube2} title={`${regressionNum} / Regression`}/>
              <div className="overflow-hidden rounded-md border border-border bg-card">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border bg-soft text-[10px] uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-5 py-3 font-medium">Suite</th>
                      <th className="px-5 py-3 text-right font-medium">Result</th>
                      <th className="hidden px-5 py-3 text-right font-medium sm:table-cell">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {([ ["Unit Tests", finding.regression.unit], ["Integration Tests", finding.regression.integration], ["Proof Tests", finding.regression.proof], ["Total", finding.regression.total] ] as const).map(([label, count]) => {
                      const allPass = count[0] === count[1];
                      return (
                        <tr key={label} className={cn("border-b border-border last:border-b-0", label === "Total" && "bg-soft font-semibold")}>
                          <td className="px-5 py-3.5">{label}</td>
                          <td className={cn("px-5 py-3.5 text-right font-mono", !allPass && "text-danger")}>{count[0]}/{count[1]}</td>
                          <td className="hidden px-5 py-3.5 text-right sm:table-cell">
                            <span className={cn("inline-flex items-center gap-1", allPass ? "text-success" : "text-danger")}>
                              {allPass ? <Check size={12}/> : <X size={12}/>}{allPass ? "Passed" : "Failed"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Final status */}
            <section className="rounded-md border border-border bg-card px-5 py-9 text-center">
              <div className="mb-4 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                Final proof status
              </div>
              <StatusBadge status={finding.final_status} large/>
              <p className="mx-auto mt-4 max-w-md text-xs leading-6 text-muted-foreground">{finding.reason}</p>
            </section>

            {/* Add test case */}
            <AddTestCaseSection tests={tests} onAdd={(t) => setTests((prev) => [...prev, t])} />

          </div>

          {/* Sticky sidebar */}
          <aside className="hidden xl:block">
            <div className="sticky top-6 rounded-md border border-border bg-card p-5">
              <div className="text-[11px] font-semibold">Verification steps</div>
              <div className="mt-5 space-y-5">
                {[
                  ["Claim",       "Suspected issue identified",                                 true],
                  ["Code evidence","Relevant line isolated",                                    true],
                  ["Reproduction", isRejected ? "Claim not reproduced" : isUnverified ? "Pending result" : "Bug reproduced", !isUnverified],
                  ["Proposed fix", finding.patch_diff.length ? isFixFailed ? "Patch verification failed" : "Patch applied" : "No patch", finding.patch_diff.length > 0 && !isFixFailed],
                  ["Adversarial",  `${passed}/${tests.length} checks passed`,                  passed === tests.length],
                  ["Regression",   "Test suites checked",                                      finding.regression.total[0] === finding.regression.total[1]],
                ].map(([name, detail, done], index) => (
                  <div key={String(name)} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className={cn(
                        "flex size-5 shrink-0 items-center justify-center rounded-full border",
                        done ? "border-success/30 bg-success/10 text-success" : isFixFailed ? "border-danger/30 bg-danger/10 text-danger" : "border-border bg-soft text-muted-foreground",
                      )}>
                        {done ? <Check size={11}/> : isFixFailed ? <X size={11}/> : <span className="size-1 rounded-full bg-current"/>}
                      </span>
                      {index < 5 && <span className="mt-1 h-5 w-px bg-border"/>}
                    </div>
                    <div>
                      <div className={cn("text-[11px] font-medium", !done && "text-muted-foreground")}>{String(name)}</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">{String(detail)}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-6 border-t border-border pt-4">
                <div className="text-[10px] text-muted-foreground">Finding ID</div>
                <div className="mt-1 font-mono text-xs">{finding.id}</div>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between gap-4 border-t border-border pt-6">
        <ButtonLink to="/findings"><ArrowLeft size={13}/> All findings</ButtonLink>
        <ButtonLink to="/findings/$id" params={{ id: next.id }}>Next finding <ArrowRight size={13}/></ButtonLink>
      </div>
    </div>
  );
}
