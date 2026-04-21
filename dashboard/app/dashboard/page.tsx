"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { useSpring, useTransform } from "framer-motion";
import {
  DollarSign, FolderKanban, AlertTriangle, XCircle,
  ArrowRight, CheckCircle, CalendarRange,
} from "lucide-react";
import Link from "next/link";
import { Shell } from "@/components/shell";
import { BurnBar } from "@/components/burn-bar";
import { api, type Project, type UsageSummary, type UsageBreakdown, type DailySpend } from "@/lib/api";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, AreaChart, Area, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";

type Period = "all" | "month" | "7d" | "today" | "custom";

const PERIOD_LABELS: Record<Exclude<Period, "custom">, string> = {
  all:   "All time",
  month: "This month",
  "7d":  "Last 7 days",
  today: "Today",
};

function getPeriodRange(period: Exclude<Period, "custom">): { from: string | null; to: string | null } {
  const now = new Date();
  if (period === "all")   return { from: null, to: null };
  if (period === "today") return { from: now.toISOString().slice(0, 10), to: null };
  if (period === "7d") {
    const d = new Date(now);
    d.setDate(d.getDate() - 6);
    return { from: d.toISOString().slice(0, 10), to: null };
  }
  return { from: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`, to: null };
}

const STAGGER = {
  container: { hidden: {}, show: { transition: { staggerChildren: 0.08 } } },
  item: {
    hidden: { opacity: 0, y: 14 },
    show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] as [number,number,number,number] } },
  },
};

function AnimatedDollar({ value }: { value: number }) {
  const spring = useSpring(0, { stiffness: 70, damping: 20 });
  const display = useTransform(spring, (v) => `$${v.toFixed(4)}`);
  useEffect(() => { spring.set(value); }, [value, spring]);
  return <motion.span className="font-mono">{display}</motion.span>;
}

interface ProjectWithUsage extends Project { usage: UsageSummary | null }

const PROVIDER_COLORS: Record<string, string> = {
  openai:    "#10a37f",
  anthropic: "#d4622a",
  google:    "#4285f4",
  deepseek:  "#5c67f2",
  ollama:    "#22c55e",
};

function LocalVsCloudWidget({ breakdown }: { breakdown: UsageBreakdown | null }) {
  if (!breakdown || breakdown.total_calls === 0) {
    return (
      <div className="card-base p-5 flex flex-col gap-3">
        <p className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600">Local vs Cloud</p>
        <p className="text-xs text-[--muted-fg] mt-2">No calls yet</p>
      </div>
    );
  }

  const entries = Object.entries(breakdown.providers)
    .map(([name, stats]) => ({ name, value: stats.calls, color: PROVIDER_COLORS[name] ?? "#64748b" }))
    .sort((a, b) => b.value - a.value);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5 }}
      className="card-base p-5 flex flex-col gap-4"
    >
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600">Local vs Cloud</p>
        <span className="font-mono text-xs text-[--muted-fg]">{breakdown.total_calls} calls</span>
      </div>
      <div className="flex items-center gap-4">
        {/* Mini donut */}
        <div className="shrink-0" style={{ width: 80, height: 80 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={entries}
                cx="50%" cy="50%"
                innerRadius={24} outerRadius={36}
                paddingAngle={2}
                dataKey="value"
                strokeWidth={0}
              >
                {entries.map((e, i) => (
                  <Cell key={i} fill={e.color} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <div className="card-base px-2 py-1 text-[10px]">
                      <span style={{ color: payload[0].payload.color }}>{payload[0].name}</span>
                      {" "}{payload[0].value} calls
                    </div>
                  ) : null
                }
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        {/* Legend */}
        <div className="flex flex-col gap-1.5 flex-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_6px_#22c55e]" />
              <span className="text-xs text-[--foreground]">Local (Ollama)</span>
            </div>
            <span className="font-mono text-xs text-green-400 font-600">{breakdown.local_pct.toFixed(1)}%</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[--amber] shadow-[0_0_6px_rgba(245,158,11,0.5)]" />
              <span className="text-xs text-[--foreground]">Cloud</span>
            </div>
            <span className="font-mono text-xs text-[--amber] font-600">{breakdown.cloud_pct.toFixed(1)}%</span>
          </div>
          <div className="border-t border-[--border] mt-1 pt-1.5 flex flex-col gap-1">
            {entries.map((e) => (
              <div key={e.name} className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: e.color }} />
                  <span className="text-[10px] text-[--muted-fg] capitalize">{e.name}</span>
                </div>
                <span className="font-mono text-[10px] text-[--muted-fg]">{e.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function StatusIcon({ pct }: { pct: number }) {
  if (pct >= 100) return <XCircle className="w-3.5 h-3.5 text-red-400" />;
  if (pct >= 80)  return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
  return <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
}

function StatCard({
  icon: Icon, label, value, sub, accent,
}: {
  icon: React.ElementType; label: string; value: React.ReactNode;
  sub?: string; accent?: string;
}) {
  return (
    <motion.div variants={STAGGER.item} className="card-base p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg]">{label}</span>
        <div
          className="flex items-center justify-center w-8 h-8 rounded-md"
          style={{ background: accent ? `${accent}18` : "rgba(255,255,255,0.05)" }}
        >
          <Icon className="w-4 h-4" style={{ color: accent ?? "var(--muted-fg)" }} strokeWidth={1.8} />
        </div>
      </div>
      <div className="font-heading font-800 text-3xl tracking-tight" style={{ color: accent ?? "var(--foreground)" }}>
        {value}
      </div>
      {sub && <p className="text-xs text-[--muted-fg]">{sub}</p>}
    </motion.div>
  );
}

export default function OverviewPage() {
  const [projects, setProjects] = useState<ProjectWithUsage[]>([]);
  const [breakdown, setBreakdown] = useState<UsageBreakdown | null>(null);
  const [dailySpend, setDailySpend] = useState<DailySpend[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>("all");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo]   = useState("");
  const [periodSpent, setPeriodSpent] = useState<number | null>(null);
  const [siteOrigin, setSiteOrigin] = useState("");

  useEffect(() => { setSiteOrigin(window.location.origin); }, []);

  useEffect(() => {
    (async () => {
      try {
        const [list, bd] = await Promise.all([
          api.projects.list(),
          api.usage.breakdown().catch(() => null),
        ]);
        const withUsage = await Promise.all(
          list.map(async (p) => {
            const usage = p.budget_usd != null
              ? await api.projects.usage(p.id).catch(() => null)
              : null;
            return { ...p, usage };
          })
        );
        setProjects(withUsage);
        setBreakdown(bd);
      } catch { /* backend offline — show empty */ }
      try {
        const daily = await api.usage.daily();
        setDailySpend(daily);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);

  const fetchPeriodSpent = useCallback(async (p: Period, from?: string, to?: string) => {
    if (p === "all") { setPeriodSpent(null); return; }
    const range = p === "custom"
      ? { from: from ?? null, to: to ?? null }
      : getPeriodRange(p);
    if (!range.from) { setPeriodSpent(null); return; }
    try {
      const history = await api.usage.history({
        date_from: range.from,
        date_to:   range.to ?? undefined,
        page_size: 1000,
      });
      setPeriodSpent(history.total_cost_usd);
    } catch { setPeriodSpent(null); }
  }, []);

  useEffect(() => {
    if (period === "custom") {
      if (customFrom) fetchPeriodSpent("custom", customFrom, customTo);
    } else {
      fetchPeriodSpent(period);
    }
  }, [period, customFrom, customTo, fetchPeriodSpent]);

  const totalSpent  = period === "all"
    ? projects.reduce((s, p) => s + (p.usage?.used_usd ?? 0), 0)
    : (periodSpent ?? 0);
  const totalBudget = projects.reduce((s, p) => s + (p.budget_usd ?? 0), 0);
  const atRisk      = projects.filter((p) => (p.usage?.pct_used ?? 0) >= 80).length;
  const exceeded    = projects.filter((p) => (p.usage?.pct_used ?? 0) >= 100).length;
  const overallPct  = totalBudget > 0 ? (totalSpent / totalBudget) * 100 : 0;

  return (
    <Shell>
      <div className="p-6 max-w-6xl">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-8"
        >
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">Overview</h1>
                  <p className="text-[--muted-fg] text-sm">
                Budget consumption across all projects ·{" "}
                <span className="text-[--foreground]">
                  {period === "custom"
                    ? (customFrom ? `${customFrom}${customTo ? ` → ${customTo}` : ""}` : "Custom range")
                    : PERIOD_LABELS[period]}
                </span>
              </p>
            </div>

            {/* Period selector */}
            <div className="flex flex-col items-end gap-2">
              <div className="flex items-center gap-1 bg-white/[0.04] border border-[--border] rounded-lg p-1">
                {(["all", "month", "7d", "today"] as Exclude<Period, "custom">[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={cn("px-3 py-1 rounded-md text-xs font-500 transition-all")}
                    style={period === p
                      ? { background: "var(--amber)", color: "#070a0f" }
                      : { color: "var(--muted-fg)" }
                    }
                  >
                    {PERIOD_LABELS[p]}
                  </button>
                ))}
                <button
                  onClick={() => setPeriod("custom")}
                  className={cn("flex items-center gap-1 px-3 py-1 rounded-md text-xs font-500 transition-all")}
                  style={period === "custom"
                    ? { background: "var(--amber)", color: "#070a0f" }
                    : { color: "var(--muted-fg)" }
                  }
                >
                  <CalendarRange className="w-3 h-3" />
                  Custom
                </button>
              </div>

              {/* Date range inputs — visibles uniquement en mode custom */}
              {period === "custom" && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-2"
                >
                  <input
                    type="date"
                    lang="en-US"
                    value={customFrom}
                    onChange={(e) => setCustomFrom(e.target.value)}
                    className="bg-[--muted] border border-[--border] rounded px-2 py-1 text-xs font-mono text-[--foreground] outline-none focus:border-[--amber]"
                    style={{ colorScheme: "dark" }}
                  />
                  <span className="text-xs text-[--muted-fg]">→</span>
                  <input
                    type="date"
                    lang="en-US"
                    value={customTo}
                    min={customFrom}
                    onChange={(e) => setCustomTo(e.target.value)}
                    className="bg-[--muted] border border-[--border] rounded px-2 py-1 text-xs font-mono text-[--foreground] outline-none focus:border-[--amber]"
                    style={{ colorScheme: "dark" }}
                  />
                </motion.div>
              )}
            </div>
          </div>
        </motion.div>

        {/* Stat cards */}
        <motion.div
          variants={STAGGER.container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
        >
          <StatCard
            icon={DollarSign} label="Total Spent"
            value={<AnimatedDollar value={totalSpent} />}
            sub={totalBudget > 0 ? `of $${totalBudget.toFixed(2)} total budget` : "No budget set"}
            accent="#f59e0b"
          />
          <StatCard
            icon={FolderKanban} label="Projects"
            value={projects.length}
            sub={`${projects.filter((p) => p.budget_usd != null).length} with budget`}
            accent="#3b82f6"
          />
          <StatCard
            icon={AlertTriangle} label="At Risk"
            value={atRisk}
            sub="≥ 80% of budget used"
            accent={atRisk > 0 ? "#f59e0b" : "#22c55e"}
          />
          <StatCard
            icon={XCircle} label="Exceeded"
            value={exceeded}
            sub="Budget limit hit"
            accent={exceeded > 0 ? "#ef4444" : "#22c55e"}
          />
        </motion.div>

        {/* Global health bar */}
        {totalBudget > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.4 }}
            className="card-base p-5 mb-6"
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-heading font-700 text-base">Global Budget Health</h2>
                <p className="text-xs text-[--muted-fg] mt-0.5">Aggregated across all budgeted projects</p>
              </div>
              <span
                className={cn(
                  "font-mono text-2xl font-600",
                  overallPct >= 100 ? "text-red-400 glow-red" :
                  overallPct >= 80  ? "text-amber-400 glow-amber" :
                  "text-green-400 glow-green"
                )}
              >
                {overallPct.toFixed(1)}%
              </span>
            </div>
            <BurnBar pct={overallPct} showValue={false} height={8} />
            <div className="flex items-center justify-between mt-2">
              <span className="font-mono text-xs text-[--muted-fg]">${totalSpent.toFixed(4)} used</span>
              <span className="font-mono text-xs text-[--muted-fg]">
                ${Math.max(0, totalBudget - totalSpent).toFixed(4)} remaining
              </span>
            </div>
          </motion.div>
        )}

        {/* Global Spend — last 30 days */}
        <div className="rounded-xl border border-[--border] bg-[--card] p-6 col-span-full mb-6">
          <h2 className="text-sm font-semibold text-[--muted] mb-4 uppercase tracking-wider">
            Global Spend — Last 30 Days
          </h2>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={dailySpend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--amber)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--amber)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} interval={6} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v: number) => `$${v.toFixed(3)}`} width={55} />
              <Tooltip
                formatter={(val) => [`$${typeof val === "number" ? val.toFixed(4) : val}`, "Spend"]}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <Area
                type="monotone"
                dataKey="spend"
                stroke="var(--amber)"
                fill="url(#spendGradient)"
                strokeWidth={2}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Local vs Cloud */}
        <div className="mb-6">
          <LocalVsCloudWidget breakdown={breakdown} />
        </div>

        {/* Projects list */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45, duration: 0.4 }}
          className="card-base"
        >
          <div className="flex items-center justify-between p-5 border-b border-[--border]">
            <h2 className="font-heading font-700 text-base">Projects</h2>
            <Link
              href="/projects"
              className="flex items-center gap-1.5 text-xs text-[--amber] hover:opacity-80 transition-opacity"
            >
              View all <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <motion.span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[--amber]"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            </div>
          ) : projects.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-[--muted-fg] text-sm mb-1">No projects yet.</p>
              <Link href="/projects" className="text-[--amber] text-sm hover:underline">
                Create your first project →
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-[--border]">
              {projects.slice(0, 6).map((p, i) => {
                const pct = p.usage?.pct_used ?? 0;
                const hasBudget = p.budget_usd != null;
                return (
                  <motion.div
                    key={p.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 + i * 0.06 }}
                  >
                    <Link
                      href={`/projects/${p.id}`}
                      className="flex items-center gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors group"
                    >
                      <div className="shrink-0"><StatusIcon pct={pct} /></div>
                      <div className="flex-1 min-w-0">
                        <p className="font-500 text-sm text-[--foreground] truncate">{p.name}</p>
                        <p className="font-mono text-[10px] text-[--muted-fg] truncate">{p.api_key.slice(0, 32)}…</p>
                      </div>
                      {hasBudget ? (
                        <div className="w-28 shrink-0">
                          <BurnBar pct={pct} showValue={false} height={4} />
                        </div>
                      ) : (
                        <span className="text-[11px] text-[--muted-fg] italic shrink-0 w-28">No budget</span>
                      )}
                      <div className="text-right shrink-0 w-20">
                        <p className="font-mono text-xs text-[--foreground]">
                          ${(p.usage?.used_usd ?? 0).toFixed(4)}
                        </p>
                        {hasBudget && (
                          <p className="font-mono text-[10px] text-[--muted-fg]">/ ${p.budget_usd!.toFixed(2)}</p>
                        )}
                      </div>
                      <div className="shrink-0 w-20 text-right">
                        <span className={cn(
                          "text-[10px] font-600 uppercase tracking-wider px-2 py-0.5 rounded-full",
                          p.action === "block"     && "bg-red-500/10 text-red-400",
                          p.action === "downgrade" && "bg-blue-500/10 text-blue-400",
                          !p.action                && "bg-white/5 text-[--muted-fg]",
                        )}>
                          {p.action ?? "—"}
                        </span>
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-[--muted-fg] shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </Link>
                  </motion.div>
                );
              })}
            </div>
          )}
        </motion.div>

        {/* Integration hint */}
        {!loading && projects.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.9 }}
            className="mt-4 px-1"
          >
            <p className="text-[11px] text-[--muted-fg]">
              Connect your app: set{" "}
              <code className="font-mono text-[--amber] bg-[--amber-dim] px-1.5 py-0.5 rounded">base_url</code>
              {" "}→{" "}
              <code className="font-mono text-[--foreground] bg-white/5 px-1.5 py-0.5 rounded">
                {siteOrigin}/proxy/openai
              </code>
            </p>
          </motion.div>
        )}
      </div>
    </Shell>
  );
}
