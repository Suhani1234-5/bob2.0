import { Link, useRouterState } from "@tanstack/react-router";
import { Activity, ArrowLeft, Braces, ChevronDown, CircleDot, ClipboardList, FileCheck2, FileDiff, GitPullRequest, LayoutDashboard, ListChecks, PanelLeftClose, PanelLeftOpen, ShieldCheck, TestTube2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/button";
import { cn } from "@/lib/utils";

const navigation = [
  { label: "Overview", icon: LayoutDashboard, href: "/" },
  { label: "Findings", icon: CircleDot, href: "/findings" },
  { label: "Agents", icon: Braces, href: "/#agents" },
  { label: "Tests", icon: TestTube2, href: "/#tests" },
  { label: "Changes", icon: FileDiff, href: "/#changes" },
  { label: "Proof Trail", icon: ShieldCheck, href: "/findings/FND-001#proof-trail" },
  { label: "Report", icon: ClipboardList, href: "/#report" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  return <div className="min-h-screen bg-background text-foreground">
    {mobileOpen && <div className="fixed inset-0 z-30 bg-background/80 lg:hidden" onClick={() => setMobileOpen(false)} />}
    <aside className={cn("fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-border bg-sidebar transition-transform lg:translate-x-0", mobileOpen ? "translate-x-0" : "-translate-x-full")}>
      <div className="flex h-[68px] items-center gap-2.5 border-b border-border px-5">
        <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground"><FileCheck2 size={18} strokeWidth={2.5} /></div>
        <span className="text-[17px] font-bold tracking-normal">Proof<span className="text-primary">PR</span></span>
        <Button variant="ghost" className="ml-auto size-8 px-0 lg:hidden" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><PanelLeftClose size={17}/></Button>
      </div>
      <div className="px-3 pt-5">
        <div className="mb-5 flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2.5">
          <div className="flex size-8 items-center justify-center rounded bg-soft text-muted-foreground"><Braces size={17}/></div>
          <div className="min-w-0 flex-1"><div className="truncate text-xs font-semibold">shop-api</div><div className="text-[10px] text-muted-foreground">Repository</div></div>
          <ChevronDown size={13} className="text-muted-foreground"/>
        </div>
        <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Workspace</div>
        <nav aria-label="Main navigation" className="space-y-0.5">
          {navigation.map(({ label, icon: Icon, href }) => {
            const active = label === "Overview" ? pathname === "/" : label === "Findings" ? pathname === "/findings" : label === "Proof Trail" ? pathname.startsWith("/findings/") : false;
            return <a key={label} href={href} onClick={() => setMobileOpen(false)} className={cn("flex h-9 items-center gap-3 rounded-md px-3 text-[12px] font-medium transition-colors", active ? "bg-primary/12 text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground")}><Icon size={16} strokeWidth={1.8}/><span>{label}</span>{label === "Findings" && <span className="ml-auto rounded bg-soft px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">7</span>}</a>;
          })}
        </nav>
      </div>
      <div className="mt-auto border-t border-border p-4">
        <div className="flex items-center gap-2.5 rounded-md bg-card px-3 py-3">
          <span className="relative flex size-2"><span className="absolute inline-flex size-full rounded-full bg-success/30"/><span className="relative inline-flex size-2 rounded-full bg-success"/></span>
          <div className="min-w-0"><div className="text-[11px] font-medium">Verification complete</div><div className="text-[10px] text-muted-foreground">PR #42 · just now</div></div>
        </div>
      </div>
    </aside>
    <div className="lg:pl-60">
      <div className="flex h-[68px] items-center justify-between gap-4 border-b border-border px-5 md:px-8 lg:px-10">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" className="size-8 px-0 lg:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><PanelLeftOpen size={19}/></Button>
          <Link to="/" className="hidden text-xs font-medium text-muted-foreground hover:text-foreground sm:inline">shop-api</Link><span className="hidden text-muted-foreground sm:inline">/</span>
          <div className="flex min-w-0 items-center gap-2 text-xs font-medium"><GitPullRequest size={15} className="shrink-0 text-primary"/><span className="truncate">Pull request #42</span></div>
          <span className="hidden rounded border border-border bg-card px-2 py-0.5 font-mono text-[10px] text-muted-foreground md:inline">feature/coupon-expiry</span>
        </div>
        <div className="flex shrink-0 items-center gap-2"><span className="size-1.5 rounded-full bg-success"/><span className="text-[11px] font-semibold text-success">COMPLETE</span><span className="hidden text-muted-foreground sm:inline">·</span><span className="hidden text-[11px] text-muted-foreground sm:inline">2m 34s</span></div>
      </div>
      <main className="mx-auto max-w-[1360px] px-5 pb-20 pt-8 md:px-8 md:pt-10 lg:px-10">{children}</main>
    </div>
  </div>;
}

export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div className="min-w-0"><div className="mb-2 flex items-center gap-2 font-mono text-[10px] font-medium uppercase tracking-widest text-primary"><Activity size={12}/>{eyebrow}</div><h1 className="text-[26px] font-semibold leading-tight md:text-[32px]">{title}</h1>{description && <p className="mt-2 text-[13px] text-muted-foreground">{description}</p>}</div>{action}</div>;
}

export function SectionHeading({ icon: Icon, title, aside, id }: { icon: typeof ListChecks; title: string; aside?: ReactNode; id?: string }) {
  return <div id={id} className="mb-4 flex scroll-mt-8 items-center justify-between gap-3"><h2 className="flex items-center gap-2.5 text-sm font-semibold"><Icon size={16} className="text-muted-foreground"/>{title}</h2>{aside}</div>;
}
