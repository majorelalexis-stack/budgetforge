"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, Copy, Check, TrendingDown, Zap, Key, Save, Plus, X, Calendar } from "lucide-react";
import Link from "next/link";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { BudgetRing } from "@/components/budget-ring";
import { QuickIntegration } from "@/components/quick-integration";
import { BurnBar } from "@/components/burn-bar";
import { ModelSelect } from "@/components/model-select";
import { cn } from "@/lib/utils";

const PROVIDER_COLORS: Record<string, string> = {
  openai: "#10a37f", anthropic: "#d4622a", google: "#4285f4",
  deepseek: "#5c67f2", ollama: "#22c55e",
};

const ALL_PROVIDERS = ["openai", "anthropic", "google", "deepseek", "ollama"] as const;

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai:    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini"],
  anthropic: ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
  google:    ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
  deepseek:  ["deepseek-chat", "deepseek-reasoner"],
  ollama:    ["llama3", "mistral", "gemma4:31b", "qwen3"],
};

const DEMO_DAILY = Array.from({ length: 30 }, (_, i) => {
  const d = new Date("2026-03-23");
  d.setDate(d.getDate() + i);
  const label = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const spend = i < 5 ? 0 : Math.max(0, 0.8 + Math.sin(i * 0.7) * 0.5 + Math.random() * 0.4);
  return { date: label, spend: parseFloat(spend.toFixed(6)) };
});

const DEMO_PROVIDERS = [
  { name: "openai",    value: 22.15, calls: 312, color: "#10a37f" },
  { name: "anthropic", value: 15.48, calls: 187, color: "#d4622a" },
  { name: "google",    value: 7.60,  calls: 95,  color: "#4285f4" },
];

const DEMO_AGENTS = [
  { name: "web-scraper",    calls: 214, cost: 22.10 },
  { name: "content-gen",    calls: 180, cost: 15.80 },
  { name: "code-assistant", calls: 200, cost: 7.33 },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="p-1.5 rounded-md text-[--muted-fg] hover:text-[--amber] hover:bg-[--amber-dim] transition-all"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
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

export default function DemoProjectPage() {
  const [action, setAction]               = useState<"block" | "downgrade">("downgrade");
  const [budgetUsd, setBudgetUsd]         = useState("150");
  const [threshold, setThreshold]         = useState("80");
  const [allowedProviders, setAllowedProviders] = useState<string[]>([]);
  const [downgradeChain, setDowngradeChain] = useState([
    "anthropic/claude-opus-4-7",
    "anthropic/claude-3-5-sonnet-20241022",
    "ollama/gemma4:31b",
  ]);
  const [saved, setSaved] = useState(false);

  const USED    = 45.23;
  const BUDGET  = parseFloat(budgetUsd) || 150;
  const PCT     = Math.min(100, (USED / BUDGET) * 100);
  const API_KEY = "bf-demo-xxxxxxxxxxxxxxxx";

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <Link href="/demo/projects" className="flex items-center gap-1.5 text-xs text-[--muted-fg] hover:text-[--foreground] transition-colors mb-4 w-fit">
          <ArrowLeft className="w-3.5 h-3.5" /> Projects
        </Link>
        <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">My AI Assistant</h1>
        <div className="flex items-center gap-2">
          <code className="font-mono text-xs text-[--muted-fg] bg-white/5 px-2 py-0.5 rounded">{API_KEY}</code>
          <CopyButton text={API_KEY} />
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column */}
        <div className="flex flex-col gap-4">
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }} className="card-base p-6 flex flex-col items-center gap-5">
            <p className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600">Budget Usage</p>
            <BudgetRing pct={PCT} used={USED} budget={BUDGET} size={168} strokeWidth={12} />
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="card-base divide-y divide-[--border]">
            {[
              { icon: Zap,          label: "Remaining", value: `$${(BUDGET - USED).toFixed(4)}`,  color: "#22c55e" },
              { icon: TrendingDown, label: "Action",    value: action,                              color: action === "block" ? "#ef4444" : "#3b82f6" },
              { icon: Key,          label: "Alert at",  value: `${threshold}%`,                    color: "#f59e0b" },
            ].map(({ icon: Icon, label, value, color }) => (
              <div key={label} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-2 text-xs text-[--muted-fg]">
                  <Icon className="w-3.5 h-3.5" style={{ color }} strokeWidth={1.8} />
                  {label}
                </div>
                <span className="font-mono text-xs font-500 capitalize" style={{ color }}>{value}</span>
              </div>
            ))}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28 }} className="card-base p-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600 mb-1">Forecast</p>
              <p className="font-mono font-700 text-xl text-green-400">~12d</p>
              <p className="text-[10px] text-[--muted-fg]">until budget exhausted</p>
            </div>
            <Calendar className="w-5 h-5 text-green-400 shrink-0" strokeWidth={1.5} />
          </motion.div>
        </div>

        {/* Right column */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Chart */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card-base p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-heading font-700 text-sm">Daily Spend (last 30 days)</h2>
              <span className="font-mono text-xs text-[--muted-fg]">Total: ${USED.toFixed(4)}</span>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={DEMO_DAILY} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="amberGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#4a6080" }} tickLine={false} axisLine={false} interval={6} />
                <YAxis tick={{ fontSize: 9, fill: "#4a6080" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toFixed(2)}`} width={50} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="spend" stroke="#f59e0b" strokeWidth={2} fill="url(#amberGrad)" dot={false} activeDot={{ r: 4, fill: "#f59e0b", strokeWidth: 0 }} />
              </AreaChart>
            </ResponsiveContainer>
          </motion.div>

          {/* Provider breakdown */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="card-base p-5">
            <h2 className="font-heading font-700 text-sm mb-4">Provider Breakdown</h2>
            <div className="flex items-center gap-5">
              <div className="shrink-0" style={{ width: 100, height: 100 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={DEMO_PROVIDERS} cx="50%" cy="50%" innerRadius={28} outerRadius={42} paddingAngle={2} dataKey="value" strokeWidth={0}>
                      {DEMO_PROVIDERS.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-col gap-2 flex-1">
                {DEMO_PROVIDERS.map((e) => (
                  <div key={e.name} className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: e.color }} />
                      <span className="text-xs text-[--foreground] capitalize">{e.name}</span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="font-mono text-[10px] text-[--muted-fg]">{e.calls}×</span>
                      <span className="font-mono text-xs font-600" style={{ color: e.color }}>${e.value.toFixed(4)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          {/* Agent breakdown */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="card-base p-5">
            <h2 className="font-heading font-700 text-sm mb-3">Agent Breakdown</h2>
            <div className="divide-y divide-[--border]">
              {DEMO_AGENTS.map((a) => (
                <div key={a.name} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-[--amber]" />
                    <span className="text-xs font-mono text-[--foreground]">{a.name}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-[10px] text-[--muted-fg]">{a.calls} calls</span>
                    <span className="font-mono text-xs font-600 text-[--amber]">${a.cost.toFixed(4)}</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Budget config */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="card-base p-5">
            <h2 className="font-heading font-700 text-sm mb-4">Budget Configuration</h2>
            <form onSubmit={handleSave} className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-[--muted-fg] block mb-1.5">Monthly budget ($)</label>
                  <input
                    type="number" step="0.01" value={budgetUsd}
                    onChange={(e) => setBudgetUsd(e.target.value)}
                    className="w-full bg-[--muted] border border-[--border] rounded-md px-3 py-2 text-sm font-mono text-[--foreground] focus:outline-none focus:border-[--amber] transition-colors"
                  />
                </div>
                <div>
                  <label className="text-xs text-[--muted-fg] block mb-1.5">Alert threshold (%)</label>
                  <input
                    type="number" value={threshold}
                    onChange={(e) => setThreshold(e.target.value)}
                    className="w-full bg-[--muted] border border-[--border] rounded-md px-3 py-2 text-sm font-mono text-[--foreground] focus:outline-none focus:border-[--amber] transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-[--muted-fg] block mb-2">On budget exceeded</label>
                <div className="grid grid-cols-2 gap-2">
                  {(["block", "downgrade"] as const).map((opt) => (
                    <button key={opt} type="button" onClick={() => setAction(opt)}
                      className={cn("flex flex-col items-start gap-1 p-3 rounded-md border text-left transition-all",
                        action === opt
                          ? opt === "block" ? "border-red-500/50 bg-red-500/10" : "border-blue-500/50 bg-blue-500/10"
                          : "border-[--border] hover:border-white/20 bg-transparent"
                      )}>
                      <span className={cn("text-xs font-600 capitalize", action === opt ? opt === "block" ? "text-red-400" : "text-blue-400" : "text-[--foreground]")}>{opt}</span>
                      <span className="text-[10px] text-[--muted-fg] leading-relaxed">
                        {opt === "block" ? "Return 429 — hard stop all calls" : "Swap to cheaper model automatically"}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {action === "downgrade" && (
                <div className="pt-3 border-t border-[--border]">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs text-[--muted-fg]">Fallback model chain <span className="text-[10px]">(ordered priority)</span></label>
                    <button type="button" onClick={() => setDowngradeChain((c) => [...c, "gpt-4o-mini"])}
                      className="flex items-center gap-1 text-[10px] text-[--amber] hover:opacity-80">
                      <Plus className="w-3 h-3" /> Add
                    </button>
                  </div>
                  <div className="flex flex-col gap-2">
                    {downgradeChain.map((model, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-[--muted-fg] w-4 shrink-0">{idx + 1}.</span>
                        <ModelSelect value={model} onChange={(val) => setDowngradeChain((c) => { const n = [...c]; n[idx] = val; return n; })} modelsByProvider={MODELS_BY_PROVIDER} className="flex-1" />
                        {downgradeChain.length > 1 && (
                          <button type="button" onClick={() => setDowngradeChain((c) => c.filter((_, i) => i !== idx))} className="text-[--muted-fg] hover:text-red-400 transition-colors shrink-0">
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-3 border-t border-[--border]">
                <label className="text-xs text-[--muted-fg] block mb-2">Allowed providers <span className="text-[10px]">(empty = all)</span></label>
                <div className="flex flex-wrap gap-2">
                  {ALL_PROVIDERS.map((p) => {
                    const active = allowedProviders.includes(p);
                    return (
                      <button key={p} type="button"
                        onClick={() => setAllowedProviders((prev) => active ? prev.filter((x) => x !== p) : [...prev, p])}
                        className={cn("flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-500 border transition-all",
                          active ? "border-transparent text-[#070a0f]" : "border-[--border] text-[--muted-fg] hover:border-white/20"
                        )}
                        style={active ? { backgroundColor: PROVIDER_COLORS[p] } : undefined}>
                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: PROVIDER_COLORS[p] }} />
                        {p}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="pt-2 border-t border-[--border]">
                <p className="text-[10px] text-[--muted-fg] mb-2">Preview</p>
                <BurnBar pct={PCT} height={6} />
              </div>

              <button type="submit" style={{ backgroundColor: "var(--amber)" }}
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-md text-sm font-600 text-[#070a0f] hover:brightness-110 shadow-[0_0_20px_rgba(245,158,11,0.35)] transition-all">
                {saved ? <Check className="w-4 h-4" /> : <><Save className="w-4 h-4" /> Save budget</>}
              </button>
            </form>
          </motion.div>

          {/* Quick Integration */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55 }} className="card-base p-5">
            <h2 className="font-heading font-700 text-sm mb-4">How to connect your tool</h2>
            <QuickIntegration
              apiKey={API_KEY}
              proxyBase="https://llmbudget.maxiaworld.app"
            />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
