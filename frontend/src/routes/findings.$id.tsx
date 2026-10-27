import { createFileRoute, Link, useParams } from "@tanstack/react-router";
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
import { getFindingDetail, getFindingEvidence, getFindingTests, getFindingPatch } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/findings/$id")({
  head: () => ({ meta: [{ title: "Proof | BobSpot" }] }),
  component: FindingDetail,
});

// ─── Code Evidence (simplified — no full-file toggle yet, no data for it) ─────
function CodeEvidence({ finding, evidenceContent }: { finding: any; evidenceContent: string }) {
  return (
    <div className="overflow-x-auto rounded-md border border-code-border bg-code">
      <div className="flex min-w-max items-center justify-between border-b border-code-border px-4 py-2.5">
        <span className="font-mono text-[10px] text-muted-foreground">{finding.file}</span>
        <span className="font-mono text-[10px] text-muted-foreground">TypeScript</span>
      </div>
      <div className="min-w-max py-3 px-5 font-mono text-[11px] leading-7 md:text-xs">
        <pre className="whitespace-pre-wrap text-foreground/80">{evidenceContent || "No code evidence recorded."}</pre>
      </div>
    </div>
  );
}

// ─── Patch diff (raw text, her diff isn't structured as added/removed rows) ──
function PatchDiff({ diffText, file }: { diffText: string; file: string }) {
  return (
    <div className="overflow-x-auto rounded-md border border-code-border bg-code">
      <div className="flex min-w-max items-center justify-between border-b border-code-border px-4 py-2.5">
        <span className="font-mono text-[10px] text-muted-foreground">{file}</span>
      </div>
      <div className="min-w-max py-3 px-5 font-mono text-[11px] leading-7 md:text-xs">
        {diffText.split("\n").map((line, i) => (
          <div key={i} className={cn(
            "whitespace-pre",
            line.startsWith("+") && "text-success bg-highlight-green",
            line.startsWith("-") && "text-danger bg-highlight-red",
          )}>
            {line}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Add Test Case form (unchanged — already local-only, no DB needed) ───────
type AdversarialTest = { name: string; passed: boolean };
type TestFormState = { scenario: string; expected: string; actual: string };

const BOB_SAMPLE: TestFormState = {
  scenario: "Apply coupon with expiresAt exactly equal to current timestamp",
  expected: "Request rejected",
  actual: "Request rejected",
};

function AddTestCaseSection({ tests, onAdd }: { tests: AdversarialTest[]; onAdd: (t: AdversarialTest) => void }) {
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
        <p className="mb-4 text-[11px] text-muted-foreground">Describe a new adversarial scenario to add to this finding's verification checks.</p>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Scenario description</label>
            <input value={form.scenario} onChange={(e) => setForm((f) => ({ ...f, scenario: e.target.value }))} placeholder="e.g. Apply expired coupon at exact boundary timestamp" className={field} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Expected result</label>
              <input value={form.expected} onChange={(e) => setForm((f) => ({ ...f, expected: e.target.value }))} placeholder="e.g. Request rejected" className={field} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Actual result</label>
              <input value={form.actual} onChange={(e) => setForm((f) => ({ ...f, actual: e.target.value }))} placeholder="e.g. Request rejected" className={field} />
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={handleSave} disabled={!form.scenario.trim()}><Check size={13} /> Save test case</Button>
          <Button variant="outline" onClick={handleGenerate} className="gap-1.5" title="Inserts a placeholder AI-generated test case"><Sparkles size={13} className="text-primary" /> Generate with Bob</Button>
          {saved && <span className="flex items-center gap-1 text-[11px] text-success"><CheckCircle2 size={13} /> Test case added</span>}
        </div>
        {tests.length > 0 && (
          <div className="mt-5 border-t border-border pt-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">All adversarial checks ({tests.length})</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {tests.map((test) => (
                <div key={test.name} className="flex min-h-11 items-center gap-2.5 rounded-md border border-border bg-soft px-3.5 py-2.5">
                  <span className={test.passed ? "text-success" : "text-warning"}>{test.passed ? <Check size={14} /> : <CircleAlert size={14} />}</span>
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

// ─── FIX FAILED banner (unchanged) ────────────────────────────────────────────
function FixFailedBanner({ failingChecks }: { failingChecks?: string[] }) {
  return (
    <div className="mb-8 rounded-md border border-danger/40 bg-danger/8 px-5 py-4">
      <div className="flex items-start gap-3">
        <TriangleAlert size={17} className="mt-0.5 shrink-0 text-danger" />
        <div className="min-w-0">
          <div className="text-sm font-semibold text-danger">Automated fix did not pass verification — requires developer review</div>
          <p className="mt-1 text-[11px] text-danger/80">The proposed patch was applied but one or more adversarial or regression checks still fail. Manual intervention is needed before this finding can be closed.</p>
          {failingChecks && failingChecks.length > 0 && (
            <div className="mt-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-danger/70">Failing checks</div>
              <ul className="space-y-1">{failingChecks.map((check) => <li key={check} className="flex items-center gap-2 font-mono text-[11px] text-danger/90"><X size={11} className="shrink-0" />{check}</li>)}</ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main detail component ────────────────────────────────────────────────────
function FindingDetail() {
  const { id } = useParams({ from: "/findings/$id" });
  const [finding, setFinding] = useState<any>(null);
  const [evidence, setEvidence] = useState<any[]>([]);
  const [testExecutions, setTestExecutions] = useState<any[]>([]);
  const [patch, setPatch] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tests, setTests] = useState<AdversarialTest[]>([]);

  useEffect(() => {
    Promise.all([
      getFindingDetail(id),
      getFindingEvidence(id),
      getFindingTests(id),
      getFindingPatch(id),
    ])
      .then(([findingData, evidenceData, testsData, patchData]) => {
        setFinding(findingData);
        setEvidence(evidenceData);
        setTestExecutions(testsData);
        setPatch(patchData?.diff ? patchData : null);
        setTests(
          testsData
            .filter((t: any) => t.test_type === "adversarial")
            .map((t: any) => ({ name: t.test_name, passed: t.status === "pass" }))
        );
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  if (!finding) return (
    <div className="py-20 text-center">
      <h1 className="text-2xl font-semibold">Finding not found</h1>
      <ButtonLink to="/findings" className="mt-5">Back to findings</ButtonLink>
    </div>
  );

  const status = (finding.status ?? "").toLowerCase();
  const isRejected = status === "rejected";
  const isUnverified = status === "unverified";
  const isFixFailed = status === "fix_failed";

  const reproductionTest = testExecutions.find((t) => t.test_type === "reproduction");
  const passed = tests.filter((t) => t.passed).length;
  const evidenceItem = evidence[0];

  return (
    <div className="mx-auto max-w-[1080px]">
      <div className="mb-7 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <Link to="/findings" className="flex items-center gap-1.5 hover:text-foreground"><ArrowLeft size={13}/> Findings</Link>
        <ChevronRight size={12}/>
        <span className="font-mono text-foreground">#{finding.id}</span>
      </div>

      <div className="mb-8 border-b border-border pb-8">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SeverityBadge severity={finding.severity}/>
          <span className="text-muted-foreground">·</span>
          <span className="font-mono text-[11px] text-muted-foreground">{finding.file}:{finding.line}</span>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <h1 className="text-[26px] font-semibold leading-tight md:text-[34px]">{finding.title}</h1>
            <p className="mt-3 text-xs text-muted-foreground">Verified against <span className="font-medium text-foreground">shop-api</span></p>
          </div>
          <StatusBadge status={finding.status} large/>
        </div>
      </div>

      {isFixFailed && <FixFailedBanner failingChecks={[]} />}

      <div id="proof-trail" className="scroll-mt-8">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex size-7 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-primary"><ShieldCheck size={15}/></div>
          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Proof trail</span>
          <div className="h-px flex-1 bg-border"/>
        </div>

        <div className="grid gap-x-8 gap-y-8 xl:grid-cols-[minmax(0,1fr)_260px]">
          <div className="min-w-0 space-y-9">

            <section>
              <SectionHeading icon={CircleAlert} title="01 / Claim"/>
              <div className="rounded-md border border-border bg-card p-5">
                <p className="text-[13px] leading-7 text-foreground/85">{finding.claim}</p>
              </div>
            </section>

            <section>
              <SectionHeading icon={Code2} title="02 / Code evidence" aside={<span className="font-mono text-[10px] text-muted-foreground">LINE {finding.line}</span>}/>
              <CodeEvidence finding={finding} evidenceContent={evidenceItem?.content ?? ""}/>
              <p className="mt-2.5 text-[11px] text-muted-foreground">{evidenceItem?.description}</p>
            </section>

            {reproductionTest && (
              <section>
                <SectionHeading
                  icon={FlaskConical}
                  title="03 / Reproduction"
                  aside={<span className={cn("rounded border px-2 py-1 font-mono text-[10px] font-semibold", reproductionTest.status === "pass" ? "border-success/30 bg-success/10 text-success" : "border-danger/30 bg-danger/10 text-danger")}>
                    {reproductionTest.status === "pass" ? "REPRODUCED" : "NOT REPRODUCED"}
                  </span>}
                />
                <div className="overflow-hidden rounded-md border border-border bg-card">
                  <div className="border-b border-border bg-soft px-5 py-3 font-mono text-[11px] text-foreground">{reproductionTest.test_name}</div>
                  <div className="space-y-4 p-5">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Expected</div>
                        <p className="text-xs leading-6 text-success">{reproductionTest.expected_result}</p>
                      </div>
                      <div>
                        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Actual</div>
                        <p className="text-xs leading-6 text-foreground/85">{reproductionTest.actual_result}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {isRejected && evidenceItem && (
              <section>
                <SectionHeading icon={ShieldCheck} title="04 / Evidence discovered"/>
                <div className="rounded-md border border-danger/20 bg-danger/5 p-5">
                  <p className="text-xs leading-7 text-foreground/85">{evidenceItem.description}</p>
                </div>
              </section>
            )}

            {patch && (
              <section id="patch" className="scroll-mt-8">
                <SectionHeading icon={FileDiff} title="05 / Proposed fix" aside={<span className={cn("text-[10px] font-semibold", isFixFailed ? "text-danger" : "text-success")}>{patch.verification_status?.toUpperCase()}</span>}/>
                <PatchDiff diffText={patch.diff} file={finding.file}/>
              </section>
            )}

            {!isRejected && tests.length > 0 && (
              <section>
                <SectionHeading icon={GitCompareArrows} title="06 / Adversarial verification" aside={<span className={cn("font-mono text-[11px] font-semibold", passed === tests.length ? "text-success" : "text-danger")}>{passed}/{tests.length} passed</span>}/>
                <div className="grid gap-2 sm:grid-cols-2">
                  {tests.map((test) => (
                    <div key={test.name} className="flex min-h-11 items-center gap-2.5 rounded-md border border-border bg-card px-3.5 py-2.5">
                      <span className={test.passed ? "text-success" : "text-warning"}>{test.passed ? <Check size={14}/> : <CircleAlert size={14}/>}</span>
                      <span className="font-mono text-[11px] text-foreground/85">{test.name}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="rounded-md border border-border bg-card px-5 py-9 text-center">
              <div className="mb-4 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Final proof status</div>
              <StatusBadge status={finding.status} large/>
            </section>

            <AddTestCaseSection tests={tests} onAdd={(t) => setTests((prev) => [...prev, t])} />
          </div>

          <aside className="hidden xl:block">
            <div className="sticky top-6 rounded-md border border-border bg-card p-5">
              <div className="text-[11px] font-semibold">Verification steps</div>
              <div className="mt-5 space-y-5">
                {[
                  ["Claim", "Suspected issue identified", true],
                  ["Code evidence", "Relevant line isolated", true],
                  ["Reproduction", reproductionTest?.status === "pass" ? "Bug reproduced" : "Not reproduced", Boolean(reproductionTest)],
                  ["Proposed fix", patch ? "Patch applied" : "No patch", Boolean(patch)],
                  ["Adversarial", `${passed}/${tests.length} checks passed`, passed === tests.length],
                ].map(([name, detail, done], index) => (
                  <div key={String(name)} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className={cn("flex size-5 shrink-0 items-center justify-center rounded-full border", done ? "border-success/30 bg-success/10 text-success" : "border-border bg-soft text-muted-foreground")}>
                        {done ? <Check size={11}/> : <span className="size-1 rounded-full bg-current"/>}
                      </span>
                      {index < 4 && <span className="mt-1 h-5 w-px bg-border"/>}
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
                <div className="mt-1 font-mono text-xs">#{finding.id}</div>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between gap-4 border-t border-border pt-6">
        <ButtonLink to="/findings"><ArrowLeft size={13}/> All findings</ButtonLink>
      </div>
    </div>
  );
}