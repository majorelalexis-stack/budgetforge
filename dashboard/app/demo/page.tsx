"use client";

import { useEffect, useState } from "react";
import {
  DollarSign,
  FolderKanban,
  AlertTriangle,
  XCircle,
  CheckCircle,
  ExternalLink,
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

const GITHUB_URL = "https://github.com/majorelalexis-stack/budgetforge";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DemoProject {
  name: string;
  budget_usd: number;
  used_usd: number;
  pct_used: number;
  action: string | null;
}

interface DemoSummary {
  total_cost_usd: number;
  total_calls: number;
  projects_count: number;
  at_risk_count: number;
  exceeded_count: number;
}

interface DemoDaily {
  date: string;
  spend: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatusIcon({ pct }: { pct: number }) {
  if (pct >= 100) return <XCircle className="w-4 h-4 text-red-400" />;
  if (pct >= 80) return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <CheckCircle className="w-4 h-4 text-green-400" />;
}

function ActionBadge({ action }: { action: string | null }) {
  if (!action) {
    return (
      <span className="text-[10px] font-600 uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/5 text-[--muted-fg]">
        —
      </span>
    );
  }
  return (
    <span
      className={cn(
        "text-[10px] font-600 uppercase tracking-wider px-2 py-0.5 rounded-full",
        action === "block" && "bg-red-500/10 text-red-400",
        action === "downgrade" && "bg-blue-500/10 text-blue-400"
      )}
    >
      {action}
    </span>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  sub?: string;
  accent?: string;
}) {
  return (
    <div
      className="rounded-xl border p-5 flex flex-col gap-3"
      style={{ background: "var(--card)", borderColor: "var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <span
          className="text-[11px] uppercase tracking-widest font-semibold"
          style={{ color: "var(--muted-fg)" }}
        >
          {label}
        </span>
        <div
          className="flex items-center justify-center w-8 h-8 rounded-md"
          style={{ background: accent ? `${accent}18` : "rgba(255,255,255,0.05)" }}
        >
          <Icon
            className="w-4 h-4"
            style={{ color: accent ?? "var(--muted-fg)" }}
            strokeWidth={1.8}
          />
        </div>
      </div>
      <div
        className="font-heading font-bold text-3xl tracking-tight"
        style={{ color: accent ?? "var(--foreground)" }}
      >
        {value}
      </div>
      {sub && (
        <p className="text-xs" style={{ color: "var(--muted-fg)" }}>
          {sub}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DemoPage() {
  const [projects, setProjects] = useState<DemoProject[]>([]);
  const [summary, setSummary] = useState<DemoSummary | null>(null);
  const [daily, setDaily] = useState<DemoDaily[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [projectsRes, summaryRes, dailyRes] = await Promise.all([
          fetch("/api/demo/projects"),
          fetch("/api/demo/usage/summary"),
          fetch("/api/demo/usage/daily"),
        ]);
        const [projectsData, summaryData, dailyData] = await Promise.all([
          projectsRes.json() as Promise<DemoProject[]>,
          summaryRes.json() as Promise<DemoSummary>,
          dailyRes.json() as Promise<DemoDaily[]>,
        ]);
        setProjects(projectsData);
        setSummary(summaryData);
        setDaily(dailyData);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="p-6 max-w-5xl">
        {/* Page header */}
        <div className="mb-8">
          <h1
            className="font-heading font-bold text-2xl tracking-tight mb-1"
            style={{ color: "var(--foreground)" }}
          >
            Overview
          </h1>
          <p className="text-sm" style={{ color: "var(--muted-fg)" }}>
            Live demo — hardcoded data, read-only access
          </p>
        </div>

        {/* Error message */}
        {error && (
          <div className="text-center py-12 text-sm" style={{ color: "var(--muted)" }}>
            Demo data unavailable — backend offline.
          </div>
        )}

        {/* Stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={DollarSign}
            label="Total Spent"
            value={
              <span className="font-mono">
                ${(summary?.total_cost_usd ?? 0).toFixed(2)}
              </span>
            }
            sub={`${summary?.total_calls ?? 0} API calls`}
            accent="#f59e0b"
          />
          <StatCard
            icon={FolderKanban}
            label="Projects"
            value={summary?.projects_count ?? projects.length}
            sub="All with budget limits"
            accent="#3b82f6"
          />
          <StatCard
            icon={AlertTriangle}
            label="At Risk"
            value={summary?.at_risk_count ?? 0}
            sub="≥ 80% of budget used"
            accent={
              (summary?.at_risk_count ?? 0) > 0 ? "#f59e0b" : "#22c55e"
            }
          />
          <StatCard
            icon={XCircle}
            label="Exceeded"
            value={summary?.exceeded_count ?? 0}
            sub="Budget limit hit"
            accent={
              (summary?.exceeded_count ?? 0) > 0 ? "#ef4444" : "#22c55e"
            }
          />
        </div>

        {/* Area chart — 30-day spend */}
        <div
          className="rounded-xl border p-6 mb-6"
          style={{ background: "var(--card)", borderColor: "var(--border)" }}
        >
          <h2
            className="text-sm font-semibold uppercase tracking-wider mb-4"
            style={{ color: "var(--muted-fg)" }}
          >
            Global Spend — Last 30 Days
          </h2>
          {loading ? (
            <div className="flex items-center justify-center h-44">
              <p className="text-sm" style={{ color: "var(--muted-fg)" }}>
                Loading…
              </p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart
                data={daily}
                margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient
                    id="demoSpendGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="5%"
                      stopColor="var(--amber)"
                      stopOpacity={0.3}
                    />
                    <stop
                      offset="95%"
                      stopColor="var(--amber)"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "var(--muted-fg)" }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval={6}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "var(--muted-fg)" }}
                  tickFormatter={(v: number) => `$${v.toFixed(1)}`}
                  width={48}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(val) => [
                    `$${typeof val === "number" ? val.toFixed(4) : val}`,
                    "Spend",
                  ]}
                  labelFormatter={(label) => `Date: ${label}`}
                />
                <Area
                  type="monotone"
                  dataKey="spend"
                  stroke="var(--amber)"
                  fill="url(#demoSpendGradient)"
                  strokeWidth={2}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Projects table */}
        <div
          className="rounded-xl border mb-8"
          style={{ background: "var(--card)", borderColor: "var(--border)" }}
        >
          <div
            className="flex items-center justify-between px-5 py-4 border-b"
            style={{ borderColor: "var(--border)" }}
          >
            <h2 className="font-heading font-bold text-base">Projects</h2>
            <span
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{
                background: "rgba(255,255,255,0.05)",
                color: "var(--muted-fg)",
              }}
            >
              Read only
            </span>
          </div>

          {loading ? (
            <div className="py-12 text-center">
              <p className="text-sm" style={{ color: "var(--muted-fg)" }}>
                Loading…
              </p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "var(--border)" }}>
              {projects.map((project) => (
                <div
                  key={project.name}
                  className="flex items-center gap-4 px-5 py-4"
                >
                  {/* Status icon */}
                  <div className="shrink-0">
                    <StatusIcon pct={project.pct_used} />
                  </div>

                  {/* Name */}
                  <div className="flex-1 min-w-0">
                    <p
                      className="font-medium text-sm truncate"
                      style={{ color: "var(--foreground)" }}
                    >
                      {project.name}
                    </p>
                    <p
                      className="font-mono text-[10px] mt-0.5"
                      style={{ color: "var(--muted-fg)" }}
                    >
                      {project.pct_used.toFixed(1)}% used
                    </p>
                  </div>

                  {/* Burn bar */}
                  <div className="w-32 shrink-0">
                    <BurnBar pct={project.pct_used} showValue={false} height={4} />
                  </div>

                  {/* Amounts */}
                  <div className="text-right shrink-0 w-24">
                    <p
                      className="font-mono text-xs"
                      style={{ color: "var(--foreground)" }}
                    >
                      ${project.used_usd.toFixed(2)}
                    </p>
                    <p
                      className="font-mono text-[10px]"
                      style={{ color: "var(--muted-fg)" }}
                    >
                      / ${project.budget_usd.toFixed(2)}
                    </p>
                  </div>

                  {/* Action badge */}
                  <div className="shrink-0 w-20 text-right">
                    <ActionBadge action={project.action} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Bottom CTA */}
        <div
          className="rounded-xl border p-8 text-center"
          style={{ background: "var(--card)", borderColor: "var(--border)" }}
        >
          <h3
            className="font-heading font-bold text-xl mb-2"
            style={{ color: "var(--foreground)" }}
          >
            Like what you see?
          </h3>
          <p
            className="text-sm mb-5 max-w-sm mx-auto"
            style={{ color: "var(--muted-fg)" }}
          >
            Self-host BudgetForge for free and put hard limits on every LLM API
            call your team makes.
          </p>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90"
            style={{ background: "var(--amber)", color: "#070a0f" }}
          >
            Self-host BudgetForge for free
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
    </div>
  );
}
