"use client";

import {
  DollarSign,
  FolderKanban,
  AlertTriangle,
  XCircle,
  CheckCircle,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { BurnBar } from "@/components/burn-bar";
import { cn } from "@/lib/utils";
import Link from "next/link";

// ── Hardcoded demo data ────────────────────────────────────────────────────

const SUMMARY = {
  total_cost_usd: 681.27,
  total_calls: 1_247,
  projects_count: 5,
  at_risk_count: 2,
  exceeded_count: 1,
};

const PROJECTS = [
  { slug: "ai-chat-assistant",  name: "AI Chat Assistant",  budget: 150, used: 108.45, pct: 72.3,  action: "downgrade" },
  { slug: "content-generator",  name: "Content Generator",  budget: 300, used: 305.80, pct: 101.9, action: "block" },
  { slug: "web-scraper-agent",  name: "Web Scraper Agent",  budget: 75,  used: 64.80,  pct: 86.4,  action: "downgrade" },
  { slug: "image-analysis",     name: "Image Analysis",     budget: 200, used: 163.55, pct: 81.8,  action: "downgrade" },
  { slug: "code-review-bot",    name: "Code Review Bot",    budget: 100, used: 38.67,  pct: 38.7,  action: "block" },
];

const DAILY = Array.from({ length: 30 }, (_, i) => {
  const d = new Date("2026-03-26");
  d.setDate(d.getDate() + i);
  const date = d.toISOString().slice(0, 10);
  const base = i < 3 ? 0 : 14 + Math.sin(i * 0.6) * 6 + (i > 20 ? 8 : 0);
  const spend = Math.max(0, base + (Math.random() - 0.5) * 4);
  return { date, spend: parseFloat(spend.toFixed(4)) };
});

// ── Sub-components ─────────────────────────────────────────────────────────

function StatusIcon({ pct }: { pct: number }) {
  if (pct >= 100) return <XCircle className="w-4 h-4 text-red-400" />;
  if (pct >= 80)  return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <CheckCircle className="w-4 h-4 text-green-400" />;
}

function ActionBadge({ action }: { action: string }) {
  return (
    <span className={cn(
      "text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full",
      action === "block"     && "bg-red-500/10 text-red-400",
      action === "downgrade" && "bg-blue-500/10 text-blue-400",
    )}>
      {action}
    </span>
  );
}

function StatCard({
  icon: Icon, label, value, sub, accent,
}: {
  icon: React.ElementType; label: string; value: React.ReactNode; sub?: string; accent?: string;
}) {
  return (
    <div className="rounded-xl border p-5 flex flex-col gap-3" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-widest font-semibold" style={{ color: "var(--muted-fg)" }}>{label}</span>
        <div className="flex items-center justify-center w-8 h-8 rounded-md" style={{ background: accent ? `${accent}18` : "rgba(255,255,255,0.05)" }}>
          <Icon className="w-4 h-4" style={{ color: accent ?? "var(--muted-fg)" }} strokeWidth={1.8} />
        </div>
      </div>
      <div className="font-heading font-bold text-3xl tracking-tight" style={{ color: accent ?? "var(--foreground)" }}>{value}</div>
      {sub && <p className="text-xs" style={{ color: "var(--muted-fg)" }}>{sub}</p>}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function DemoPage() {
  return (
    <div className="p-6 max-w-5xl">
      <div className="mb-8">
        <h1 className="font-heading font-bold text-2xl tracking-tight mb-1" style={{ color: "var(--foreground)" }}>Overview</h1>
        <p className="text-sm" style={{ color: "var(--muted-fg)" }}>Live demo — hardcoded data, read-only access</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard icon={DollarSign} label="Total Spent"
          value={<span className="font-mono">${SUMMARY.total_cost_usd.toFixed(2)}</span>}
          sub={`${SUMMARY.total_calls.toLocaleString()} API calls`} accent="#f59e0b" />
        <StatCard icon={FolderKanban} label="Projects"
          value={SUMMARY.projects_count}
          sub="All with budget limits" accent="#3b82f6" />
        <StatCard icon={AlertTriangle} label="At Risk"
          value={SUMMARY.at_risk_count}
          sub="≥ 80% of budget used" accent="#f59e0b" />
        <StatCard icon={XCircle} label="Exceeded"
          value={SUMMARY.exceeded_count}
          sub="Budget limit hit" accent="#ef4444" />
      </div>

      {/* Chart */}
      <div className="rounded-xl border p-6 mb-6" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
        <h2 className="text-sm font-semibold uppercase tracking-wider mb-4" style={{ color: "var(--muted-fg)" }}>
          Global Spend — Last 30 Days
        </h2>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={DAILY} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="demoGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="var(--amber)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--amber)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--muted-fg)" }}
              tickFormatter={(v: string) => v.slice(5)} interval={6}
              axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "var(--muted-fg)" }}
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
              width={40} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
              formatter={(val) => [`$${typeof val === "number" ? val.toFixed(2) : val}`, "Spend"]}
              labelFormatter={(l) => `Date: ${l}`}
            />
            <Area type="monotone" dataKey="spend" stroke="var(--amber)"
              fill="url(#demoGrad)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Projects table */}
      <div className="rounded-xl border mb-8" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "var(--border)" }}>
          <h2 className="font-heading font-bold text-base">Projects</h2>
          <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(255,255,255,0.05)", color: "var(--muted-fg)" }}>
            Read only
          </span>
        </div>
        <div className="divide-y" style={{ borderColor: "var(--border)" }}>
          {PROJECTS.map((p) => (
            <Link key={p.slug} href={`/demo/projects/${p.slug}`}>
              <div className="flex items-center gap-4 px-5 py-4 hover:bg-white/5 transition-colors cursor-pointer">
                <div className="shrink-0"><StatusIcon pct={p.pct} /></div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate" style={{ color: "var(--foreground)" }}>{p.name}</p>
                  <p className="font-mono text-[10px] mt-0.5" style={{ color: "var(--muted-fg)" }}>{p.pct.toFixed(1)}% used</p>
                </div>
                <div className="w-32 shrink-0"><BurnBar pct={p.pct} showValue={false} height={4} /></div>
                <div className="text-right shrink-0 w-24">
                  <p className="font-mono text-xs" style={{ color: "var(--foreground)" }}>${p.used.toFixed(2)}</p>
                  <p className="font-mono text-[10px]" style={{ color: "var(--muted-fg)" }}>/ ${p.budget.toFixed(2)}</p>
                </div>
                <div className="shrink-0 w-20 text-right"><ActionBadge action={p.action} /></div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="rounded-xl border p-8 text-center" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
        <h3 className="font-heading font-bold text-xl mb-2" style={{ color: "var(--foreground)" }}>Like what you see?</h3>
        <p className="text-sm mb-5 max-w-sm mx-auto" style={{ color: "var(--muted-fg)" }}>
          Self-host BudgetForge for free and put hard limits on every LLM API call your team makes.
        </p>
        <Link href="/portal" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90"
          style={{ background: "var(--amber)", color: "#070a0f" }}>
          Get started for free →
        </Link>
      </div>
    </div>
  );
}
