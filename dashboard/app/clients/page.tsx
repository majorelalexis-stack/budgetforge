"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Users, TrendingUp, CreditCard, Zap } from "lucide-react";
import { Shell } from "@/components/shell";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, LineChart, Line,
} from "recharts";

interface AdminStats {
  clients_by_plan: Record<string, number>;
  mrr_usd: number;
  total_clients: number;
  total_calls: number;
  total_spend_usd: number;
  signups_last_30_days: { date: string; count: number }[];
  client_growth: { date: string; total: number }[];
}

const PLAN_COLORS: Record<string, string> = {
  free:   "#64748b",
  pro:    "#3b82f6",
  agency: "#f59e0b",
};

const STAGGER = {
  container: { hidden: {}, show: { transition: { staggerChildren: 0.08 } } },
  item: {
    hidden: { opacity: 0, y: 14 },
    show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] } },
  },
};

function StatCard({
  icon: Icon, label, value, sub, accent,
}: {
  icon: React.ElementType; label: string; value: React.ReactNode; sub?: string; accent?: string;
}) {
  return (
    <motion.div variants={STAGGER.item} className="card-base p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg]">{label}</span>
        <div className="flex items-center justify-center w-8 h-8 rounded-md"
          style={{ background: accent ? `${accent}18` : "rgba(255,255,255,0.05)" }}>
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

function PlanCountCard({ plan, count }: { plan: string; count: number }) {
  const color = PLAN_COLORS[plan] ?? "#64748b";
  return (
    <motion.div variants={STAGGER.item} className="card-base p-4 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
        <span className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg]">{plan}</span>
      </div>
      <div className="font-heading font-800 text-4xl tracking-tight" style={{ color }}>
        {count}
      </div>
      <p className="text-xs text-[--muted-fg]">client{count !== 1 ? "s" : ""}</p>
    </motion.div>
  );
}

export default function ClientsPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/admin/stats")
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const planEntries = stats
    ? Object.entries(stats.clients_by_plan).filter(([, n]) => n > 0)
    : [];

  const signupTotal = stats?.signups_last_30_days.reduce((s, d) => s + d.count, 0) ?? 0;

  return (
    <Shell>
      <div className="p-6 max-w-6xl">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-8">
          <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">Clients</h1>
          <p className="text-[--muted-fg] text-sm">Business overview — signups, plans, revenue</p>
        </motion.div>

        {loading ? (
          <div className="flex items-center justify-center py-32">
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <motion.span key={i} className="w-2 h-2 rounded-full bg-[--amber]"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }} />
              ))}
            </div>
          </div>
        ) : !stats ? (
          <div className="card-base p-10 text-center text-[--muted-fg] text-sm">Failed to load stats.</div>
        ) : (
          <>
            {/* KPI cards */}
            <motion.div variants={STAGGER.container} initial="hidden" animate="show"
              className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <StatCard icon={Users} label="Total Clients" value={stats.total_clients} accent="#3b82f6"
                sub={`${signupTotal} new last 30d`} />
              <StatCard icon={TrendingUp} label="MRR" value={`$${stats.mrr_usd}`} accent="#f59e0b"
                sub={`${stats.clients_by_plan.pro ?? 0} Pro · ${stats.clients_by_plan.agency ?? 0} Agency`} />
              <StatCard icon={Zap} label="Total Calls" value={stats.total_calls.toLocaleString()} accent="#22c55e"
                sub="All time proxy calls" />
              <StatCard icon={CreditCard} label="Total Spend" value={`$${stats.total_spend_usd.toFixed(2)}`} accent="#a855f7"
                sub="Proxied through BF" />
            </motion.div>

            {/* Plan count cards */}
            <motion.div variants={STAGGER.container} initial="hidden" animate="show"
              className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {(["free", "pro", "agency"] as const).map((plan) => (
                <PlanCountCard key={plan} plan={plan} count={stats.clients_by_plan[plan] ?? 0} />
              ))}
            </motion.div>

            {/* Client growth chart */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
              className="card-base p-5 mb-6">
              <h2 className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg] mb-4">
                Client growth — last 90 days
              </h2>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={stats.client_growth} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="growthGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#c8d8e8" }} tickLine={false} axisLine={false}
                    tickFormatter={(v: string) => v.slice(5)} interval={14} />
                  <YAxis tick={{ fontSize: 9, fill: "#c8d8e8" }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11 }}
                    formatter={(v) => [v, "Total clients"]}
                    labelStyle={{ color: "#c8d8e8" }}
                  />
                  <Line type="monotone" dataKey="total" stroke="#22c55e" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </motion.div>

            {/* Signups chart */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
              className="card-base p-5 mb-6">
              <h2 className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg] mb-4">
                New signups — last 30 days
              </h2>
              <ResponsiveContainer width="100%" height={140}>
                <AreaChart data={stats.signups_last_30_days} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="signupGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#c8d8e8" }} tickLine={false} axisLine={false}
                    tickFormatter={(v: string) => v.slice(5)} interval={6} />
                  <YAxis tick={{ fontSize: 9, fill: "#c8d8e8" }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11 }}
                    formatter={(v) => [v, "Signups"]}
                    labelStyle={{ color: "#c8d8e8" }}
                  />
                  <Area type="monotone" dataKey="count" stroke="#3b82f6" fill="url(#signupGrad)" strokeWidth={1.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </motion.div>

            {/* Plans breakdown */}
            <div className="grid md:grid-cols-2 gap-4">
              {/* Bar chart */}
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
                className="card-base p-5">
                <h2 className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg] mb-4">
                  Clients by plan
                </h2>
                {planEntries.length === 0 ? (
                  <p className="text-xs text-[--muted-fg] py-8 text-center">No clients yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height={140}>
                    <BarChart data={planEntries.map(([plan, count]) => ({ plan, count }))}
                      margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                      <XAxis dataKey="plan" tick={{ fontSize: 10, fill: "#c8d8e8" }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: "#c8d8e8" }} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip
                        contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11 }}
                        formatter={(v) => [v, "Clients"]}
                        labelStyle={{ color: "#c8d8e8" }}
                      />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {planEntries.map(([plan]) => (
                          <Cell key={plan} fill={PLAN_COLORS[plan] ?? "#64748b"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </motion.div>

              {/* Plan list */}
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }}
                className="card-base p-5">
                <h2 className="text-[11px] uppercase tracking-widest font-600 text-[--muted-fg] mb-4">
                  Revenue breakdown
                </h2>
                <div className="flex flex-col gap-3">
                  {(["free", "pro", "agency"] as const).map((plan) => {
                    const count = stats.clients_by_plan[plan] ?? 0;
                    const mrr = (plan === "pro" ? 29 : plan === "agency" ? 79 : 0) * count;
                    return (
                      <div key={plan} className="flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <span className="w-2 h-2 rounded-full" style={{ background: PLAN_COLORS[plan] }} />
                          <span className="text-sm capitalize">{plan}</span>
                          <span className="text-[11px] text-[--muted-fg]">{count} client{count !== 1 ? "s" : ""}</span>
                        </div>
                        <span className="font-mono text-sm" style={{ color: mrr > 0 ? "#f59e0b" : "var(--muted-fg)" }}>
                          {mrr > 0 ? `$${mrr}/mo` : "—"}
                        </span>
                      </div>
                    );
                  })}
                  <div className="border-t border-[--border] mt-1 pt-3 flex items-center justify-between">
                    <span className="text-sm font-600">Total MRR</span>
                    <span className="font-mono font-700 text-[--amber]">${stats.mrr_usd}/mo</span>
                  </div>
                </div>
              </motion.div>
            </div>
          </>
        )}
      </div>
    </Shell>
  );
}
