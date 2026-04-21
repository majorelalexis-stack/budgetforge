"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft, Copy, Check, ShieldAlert, TrendingDown,
  Zap, Key, Save, Calendar, RefreshCw, Plus, X, GripVertical,
} from "lucide-react";
import Link from "next/link";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { Shell } from "@/components/shell";
import { BudgetRing } from "@/components/budget-ring";
import { BurnBar } from "@/components/burn-bar";
import { Toast } from "@/components/toast";
import { ModelSelect } from "@/components/model-select";
import { api, type Project, type UsageSummary, type UsageBreakdown, type AgentBreakdown, type DailySpend } from "@/lib/api";
import { cn } from "@/lib/utils";

const PROVIDER_COLORS: Record<string, string> = {
  openai:    "#10a37f",
  anthropic: "#d4622a",
  google:    "#4285f4",
  deepseek:  "#5c67f2",
  ollama:    "#22c55e",
};

const ALL_PROVIDERS = ["openai", "anthropic", "google", "deepseek", "ollama"] as const;

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai:    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"],
  anthropic: ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
  google:    ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-thinking"],
  deepseek:  ["deepseek-chat", "deepseek-reasoner"],
  ollama:    ["llama3", "mistral", "qwen3", "gemma3"],
};


function formatDailyChartData(raw: DailySpend[]) {
  return raw.map((entry) => ({
    date: new Date(entry.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    spend: entry.spend,
  }));
}

function CopyButton({ text, onCopy }: { text: string; onCopy?: () => void }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    onCopy?.();
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button
      onClick={copy}
      className="p-1.5 rounded-md text-[--muted-fg] hover:text-[--amber] hover:bg-[--amber-dim] transition-all"
      title="Copy"
    >
      {copied
        ? <Check className="w-3.5 h-3.5 text-green-400" />
        : <Copy className="w-3.5 h-3.5" />
      }
    </button>
  );
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card-base px-3 py-2 text-xs">
      <p className="text-[--muted-fg] mb-0.5">{label}</p>
      <p className="font-mono text-[--amber] font-500">${payload[0].value.toFixed(6)}</p>
    </div>
  );
}

function ForecastWidget({ forecastDays }: { forecastDays: number | null | undefined }) {
  if (forecastDays == null) return null;
  const color = forecastDays < 3 ? "#ef4444" : forecastDays < 7 ? "#f59e0b" : "#22c55e";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.28 }}
      className="card-base p-4 flex items-center justify-between"
    >
      <div>
        <p className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600 mb-1">Forecast</p>
        <p className="font-mono font-700 text-xl" style={{ color }}>
          ~{forecastDays.toFixed(0)}d
        </p>
        <p className="text-[10px] text-[--muted-fg]">until budget exhausted</p>
      </div>
      <Calendar className="w-5 h-5 shrink-0" style={{ color }} strokeWidth={1.5} />
    </motion.div>
  );
}

function ProviderBreakdownChart({ breakdown }: { breakdown: UsageBreakdown | null }) {
  if (!breakdown || breakdown.total_calls === 0) return null;

  const entries = Object.entries(breakdown.providers)
    .map(([name, stats]) => ({
      name,
      value: stats.cost_usd,
      calls: stats.calls,
      color: PROVIDER_COLORS[name] ?? "#64748b",
    }))
    .filter((e) => e.calls > 0)
    .sort((a, b) => b.value - a.value);

  if (entries.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.45 }}
      className="card-base p-5"
    >
      <h2 className="font-heading font-700 text-sm mb-4">Provider Breakdown</h2>
      <div className="flex items-center gap-5">
        <div className="shrink-0" style={{ width: 100, height: 100 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={entries}
                cx="50%" cy="50%"
                innerRadius={28} outerRadius={42}
                paddingAngle={2}
                dataKey="value"
                strokeWidth={0}
              >
                {entries.map((e, i) => <Cell key={i} fill={e.color} />)}
              </Pie>
              <Tooltip
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <div className="card-base px-2 py-1 text-[10px]">
                      <span style={{ color: payload[0].payload.color }}>{payload[0].name}</span>
                      {" "}${Number(payload[0].value).toFixed(4)}
                    </div>
                  ) : null
                }
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-col gap-2 flex-1 min-w-0">
          {entries.map((e) => (
            <div key={e.name} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: e.color }} />
                <span className="text-xs text-[--foreground] capitalize truncate">{e.name}</span>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="font-mono text-[10px] text-[--muted-fg]">{e.calls}×</span>
                <span className="font-mono text-xs font-600" style={{ color: e.color }}>
                  ${e.value.toFixed(4)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function AgentBreakdownTable({ agents }: { agents: AgentBreakdown | null }) {
  if (!agents || agents.total_calls === 0) return null;
  const rows = Object.entries(agents.agents).sort((a, b) => b[1].calls - a[1].calls);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5 }}
      className="card-base p-5"
    >
      <h2 className="font-heading font-700 text-sm mb-3">Agent Breakdown</h2>
      <div className="divide-y divide-[--border]">
        {rows.map(([name, stats]) => (
          <div key={name} className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[--amber]" />
              <span className="text-xs font-mono text-[--foreground]">{name}</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-[10px] text-[--muted-fg]">{stats.calls} call{stats.calls > 1 ? "s" : ""}</span>
              <span className="font-mono text-xs font-600 text-[--amber]">${stats.cost_usd.toFixed(4)}</span>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [breakdown, setBreakdown] = useState<UsageBreakdown | null>(null);
  const [agents, setAgents] = useState<AgentBreakdown | null>(null);
  const [dailyData, setDailyData] = useState<{ date: string; spend: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const [budgetUsd, setBudgetUsd] = useState("");
  const [threshold, setThreshold] = useState("80");
  const [thresholdError, setThresholdError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [action, setAction] = useState<"block" | "downgrade">("block");
  const [allowedProviders, setAllowedProviders] = useState<string[]>([]);
  const [downgradeChain, setDowngradeChain] = useState<string[]>(["gpt-4o-mini", "claude-haiku-4-5", "gemini-2.0-flash"]);
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, string[]>>(MODELS_BY_PROVIDER);
  const [saving, setSaving] = useState(false);

  const [toast, setToast] = useState<{ show: boolean; message: string }>({ show: false, message: "" });
  const [rotating, setRotating] = useState(false);
  function showToast(message: string) {
    setToast({ show: true, message });
  }

  async function rotateKey() {
    if (!project) return;
    if (!confirm("Rotate API key? The current key will stop working immediately.")) return;
    setRotating(true);
    try {
      await api.projects.rotateKey(project.id);
      showToast("API key rotated");
      await refresh();
    } finally {
      setRotating(false);
    }
  }

  async function refresh() {
    setRefreshError(null);
    try {
      const p = await api.projects.get(Number(id));
      const [u, bd, ag, daily] = await Promise.all([
        p.budget_usd != null ? api.projects.usage(Number(id)).catch(() => null) : null,
        api.projects.breakdown(Number(id)).catch(() => null),
        api.projects.agents(Number(id)).catch(() => null),
        api.projects.dailyUsage(Number(id)).catch(() => null),
      ]);
      setProject(p);
      setUsage(u);
      setBreakdown(bd);
      setAgents(ag);
      setDailyData(daily ? formatDailyChartData(daily) : []);
      if (p.budget_usd != null)          setBudgetUsd(String(p.budget_usd));
      if (p.alert_threshold_pct != null) setThreshold(String(p.alert_threshold_pct));
      if (p.action)                       setAction(p.action);
      setAllowedProviders(p.allowed_providers ?? []);
      if (p.downgrade_chain?.length) setDowngradeChain(p.downgrade_chain);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load project";
      if (msg.includes("404") || msg.includes("not found")) {
        router.push("/projects");
      } else {
        setRefreshError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, [id]);

  useEffect(() => {
    api.models().then((data) => {
      if (data.providers && Object.keys(data.providers).length > 0) {
        setModelsByProvider(data.providers);
      }
    }).catch(() => { /* keep fallback */ });
  }, []);

  async function saveBudget(e: React.FormEvent) {
    e.preventDefault();
    if (!project) return;
    setSaveError(null);
    setThresholdError(null);

    const parsed = parseFloat(budgetUsd);
    if (budgetUsd === "" || isNaN(parsed) || parsed < 0) {
      showToast("Enter a valid budget amount (0 or more)");
      return;
    }
    // H4: valider que threshold est un entier valide
    const thresholdParsed = parseInt(threshold, 10);
    if (isNaN(thresholdParsed) || thresholdParsed < 0 || thresholdParsed > 100) {
      setThresholdError("Alert threshold must be a number between 0 and 100");
      return;
    }

    setSaving(true);
    try {
      await api.projects.setBudget(project.id, {
        budget_usd: parsed,
        alert_threshold_pct: thresholdParsed,
        action,
        allowed_providers: allowedProviders,
        downgrade_chain: downgradeChain.filter(Boolean),
      });
      showToast("Budget saved");
      await refresh();
    } catch (err) {
      // H3: afficher l'erreur au lieu de la swallower silencieusement
      const msg = err instanceof Error ? err.message : "Failed to save budget";
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  }

  const pct      = usage?.pct_used ?? 0;
  const usedUsd  = usage?.used_usd ?? 0;
  const budgetVal = project?.budget_usd ?? 0;
  const chartData = dailyData;

  if (loading) {
    return (
      <Shell>
        <div className="flex items-center justify-center h-64">
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="w-2 h-2 rounded-full bg-[--amber]"
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
              />
            ))}
          </div>
        </div>
      </Shell>
    );
  }

  if (!project) {
    if (refreshError) {
      return (
        <Shell>
          <div className="p-6 max-w-xl">
            <p className="text-red-400 text-sm font-mono">Error: {refreshError}</p>
            <button
              onClick={() => refresh()}
              className="mt-3 text-xs text-[--amber] hover:underline"
            >
              Retry
            </button>
          </div>
        </Shell>
      );
    }
    return null;
  }

  return (
    <Shell>
      <div className="p-6 max-w-5xl">
        {/* Back + header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <Link
            href="/projects"
            className="flex items-center gap-1.5 text-xs text-[--muted-fg] hover:text-[--foreground] transition-colors mb-4 w-fit"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Projects
          </Link>
          <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">{project.name}</h1>
          <div className="flex items-center gap-2">
            <code className="font-mono text-xs text-[--muted-fg] bg-white/5 px-2 py-0.5 rounded">
              {project.api_key}
            </code>
            <CopyButton text={project.api_key} onCopy={() => showToast("API key copied")} />
            <button
              onClick={rotateKey}
              disabled={rotating}
              title="Rotate API key"
              className="p-1.5 rounded-md text-[--muted-fg] hover:text-amber-400 hover:bg-[--amber-dim] transition-all disabled:opacity-40"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${rotating ? "animate-spin" : ""}`} />
            </button>
          </div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Ring + quick stats + forecast */}
          <div className="flex flex-col gap-4">
            {/* Budget ring */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4 }}
              className="card-base p-6 flex flex-col items-center gap-5"
            >
              <p className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600">Budget Usage</p>
              {budgetVal > 0 ? (
                <BudgetRing pct={pct} used={usedUsd} budget={budgetVal} size={168} strokeWidth={12} />
              ) : (
                <div className="flex flex-col items-center gap-3 py-4">
                  <ShieldAlert className="w-10 h-10 text-[--muted-fg]" strokeWidth={1.2} />
                  <p className="text-xs text-[--muted-fg] text-center">No budget configured</p>
                </div>
              )}
            </motion.div>

            {/* Quick stats */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="card-base divide-y divide-[--border]"
            >
              {[
                { icon: Zap,          label: "Remaining", value: `$${(usage?.remaining_usd ?? 0).toFixed(4)}`,              color: "#22c55e" },
                { icon: TrendingDown, label: "Action",    value: project.action ?? "—",                                     color: project.action === "block" ? "#ef4444" : project.action === "downgrade" ? "#3b82f6" : "var(--muted-fg)" },
                { icon: Key,          label: "Alert at",  value: project.alert_threshold_pct ? `${project.alert_threshold_pct}%` : "—", color: "#f59e0b" },
              ].map(({ icon: Icon, label, value, color }) => (
                <div key={label} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-2 text-xs text-[--muted-fg]">
                    <Icon className="w-3.5 h-3.5" style={{ color }} strokeWidth={1.8} />
                    {label}
                  </div>
                  <span className="font-mono text-xs font-500" style={{ color }}>{value}</span>
                </div>
              ))}
            </motion.div>

            {/* Forecast widget — P2.2 */}
            <ForecastWidget forecastDays={usage?.forecast_days} />
          </div>

          {/* Right column: Chart + breakdown + config */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            {/* Spend chart */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="card-base p-5"
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-heading font-700 text-sm">Daily Spend (last 30 days)</h2>
                <span className="font-mono text-xs text-[--muted-fg]">
                  Total: ${usedUsd.toFixed(4)}
                </span>
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <defs>
                    <linearGradient id="amberGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 9, fill: "#4a6080" }}
                    tickLine={false}
                    axisLine={false}
                    interval={6}
                  />
                  <YAxis
                    tick={{ fontSize: 9, fill: "#4a6080", fontFamily: "var(--font-jetbrains)" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `$${v.toFixed(4)}`}
                    width={60}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="spend"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    fill="url(#amberGrad)"
                    dot={false}
                    activeDot={{ r: 4, fill: "#f59e0b", strokeWidth: 0 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </motion.div>

            {/* Provider breakdown chart — P3.1 */}
            <ProviderBreakdownChart breakdown={breakdown} />

            {/* Agent breakdown — P2.4 */}
            <AgentBreakdownTable agents={agents} />

            {/* Budget config form */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="card-base p-5"
            >
              <h2 className="font-heading font-700 text-sm mb-4">Budget Configuration</h2>
              <form onSubmit={saveBudget} className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-[--muted-fg] block mb-1.5">Monthly budget ($)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={budgetUsd}
                      onChange={(e) => setBudgetUsd(e.target.value)}
                      placeholder="100.00"
                      className={cn(
                        "w-full bg-[--muted] border border-[--border] rounded-md px-3 py-2",
                        "text-sm font-mono text-[--foreground] placeholder:text-[--muted-fg]",
                        "focus:outline-none focus:border-[--amber] transition-colors"
                      )}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-[--muted-fg] block mb-1.5">Alert threshold (%)</label>
                    <input
                      type="number"
                      value={threshold}
                      onChange={(e) => { setThreshold(e.target.value); setThresholdError(null); }}
                      className={cn(
                        "w-full bg-[--muted] border rounded-md px-3 py-2",
                        "text-sm font-mono text-[--foreground]",
                        "focus:outline-none transition-colors",
                        thresholdError ? "border-red-500" : "border-[--border] focus:border-[--amber]"
                      )}
                    />
                    {thresholdError && (
                      <p className="text-red-400 text-[10px] mt-1">{thresholdError}</p>
                    )}
                  </div>
                </div>

                {/* Action selector */}
                <div>
                  <label className="text-xs text-[--muted-fg] block mb-2">On budget exceeded</label>
                  <div className="grid grid-cols-2 gap-2">
                    {(["block", "downgrade"] as const).map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => setAction(opt)}
                        className={cn(
                          "flex flex-col items-start gap-1 p-3 rounded-md border text-left transition-all",
                          action === opt
                            ? opt === "block"
                              ? "border-red-500/50 bg-red-500/10"
                              : "border-blue-500/50 bg-blue-500/10"
                            : "border-[--border] hover:border-white/20 bg-transparent"
                        )}
                      >
                        <span className={cn(
                          "text-xs font-600 capitalize",
                          action === opt
                            ? opt === "block" ? "text-red-400" : "text-blue-400"
                            : "text-[--foreground]"
                        )}>
                          {opt}
                        </span>
                        <span className="text-[10px] text-[--muted-fg] leading-relaxed">
                          {opt === "block"
                            ? "Return 429 — hard stop all calls"
                            : "Swap to cheaper model automatically"
                          }
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Downgrade chain — visible only when action=downgrade */}
                {action === "downgrade" && (
                  <div className="pt-3 border-t border-[--border]">
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs text-[--muted-fg]">
                        Fallback model chain <span className="text-[10px]">(ordered priority)</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setDowngradeChain((c) => [...c, "gpt-4o-mini"])}
                        className="flex items-center gap-1 text-[10px] text-[--amber] hover:opacity-80 transition-opacity"
                      >
                        <Plus className="w-3 h-3" /> Add
                      </button>
                    </div>
                    <div className="flex flex-col gap-2">
                      {downgradeChain.map((model, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-[--muted-fg] w-4 shrink-0">{idx + 1}.</span>
                          <ModelSelect
                            value={model}
                            onChange={(val) => setDowngradeChain((c) => {
                              const next = [...c];
                              next[idx] = val;
                              return next;
                            })}
                            modelsByProvider={modelsByProvider}
                            className="flex-1"
                          />
                          {downgradeChain.length > 1 && (
                            <button
                              type="button"
                              onClick={() => setDowngradeChain((c) => c.filter((_, i) => i !== idx))}
                              className="text-[--muted-fg] hover:text-red-400 transition-colors shrink-0"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Allowed providers */}
                <div className="pt-3 border-t border-[--border]">
                  <label className="text-xs text-[--muted-fg] block mb-2">
                    Allowed providers <span className="text-[10px]">(empty = all)</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {ALL_PROVIDERS.map((p) => {
                      const active = allowedProviders.includes(p);
                      return (
                        <button
                          key={p}
                          type="button"
                          onClick={() =>
                            setAllowedProviders((prev) =>
                              active ? prev.filter((x) => x !== p) : [...prev, p]
                            )
                          }
                          className={cn(
                            "flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-500 border transition-all",
                            active
                              ? "border-transparent text-[#070a0f]"
                              : "border-[--border] text-[--muted-fg] hover:border-white/20"
                          )}
                          style={active ? { backgroundColor: PROVIDER_COLORS[p] } : undefined}
                        >
                          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: PROVIDER_COLORS[p] }} />
                          {p}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Budget bar preview */}
                {budgetUsd && parseFloat(budgetUsd) > 0 && (
                  <div className="pt-2 border-t border-[--border]">
                    <p className="text-[10px] text-[--muted-fg] mb-2">Preview</p>
                    <BurnBar pct={pct} height={6} />
                  </div>
                )}

                {saveError && (
                  <p className="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
                    {saveError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={saving}
                  style={{ backgroundColor: "var(--amber)" }}
                  className={cn(
                    "flex items-center justify-center gap-2 w-full py-2.5 rounded-md text-sm font-600 transition-all",
                    "text-[#070a0f] hover:brightness-110 shadow-[0_0_20px_rgba(245,158,11,0.35)]",
                    "disabled:opacity-50 disabled:cursor-not-allowed"
                  )}
                >
                  {saving ? (
                    <span className="w-4 h-4 rounded-full border-2 border-[#070a0f]/40 border-t-[#070a0f] animate-spin" />
                  ) : (
                    <><Save className="w-4 h-4" /> Save budget</>
                  )}
                </button>
              </form>
            </motion.div>

            {/* Integration snippet */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              className="card-base p-5"
            >
              <h2 className="font-heading font-700 text-sm mb-3">Quick Integration</h2>
              {(() => {
                const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";
                return (
                  <pre className="font-mono text-[11px] bg-black/30 rounded-md p-4 overflow-x-auto text-[--foreground] leading-relaxed">
                    <span className="text-[--muted-fg]"># Python / OpenAI SDK</span>{"\n"}
                    <span className="text-[#22c55e]">client</span>
                    {" = openai.OpenAI(\n"}
                    {"    "}
                    <span className="text-[--amber]">base_url</span>
                    {`="${baseUrl}/proxy/openai",\n`}
                    {"    "}
                    <span className="text-[--amber]">api_key</span>
                    {`="`}
                    <span className="text-blue-400">{project.api_key}</span>
                    {`",\n)\n`}
                    <span className="text-[--muted-fg]"># Anthropic SDK</span>{"\n"}
                    <span className="text-[#22c55e]">client</span>
                    {" = anthropic.Anthropic(\n"}
                    {"    "}
                    <span className="text-[--amber]">base_url</span>
                    {`="${baseUrl}/proxy/anthropic",\n`}
                    {"    "}
                    <span className="text-[--amber]">api_key</span>
                    {`="`}
                    <span className="text-blue-400">{project.api_key}</span>
                    {`",\n)`}
                  </pre>
                );
              })()}
              <p className="text-[10px] text-[--muted-fg] mt-2">
                Your LLM API key stays in the backend. Only the BudgetForge key goes in client code.
              </p>
            </motion.div>
          </div>
        </div>
      </div>

      {/* Toast — P3.3 */}
      <Toast
        show={toast.show}
        message={toast.message}
        onClose={() => setToast({ show: false, message: "" })}
      />
    </Shell>
  );
}
