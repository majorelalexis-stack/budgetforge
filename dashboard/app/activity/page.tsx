"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity, ChevronLeft, ChevronRight, Download,
  RefreshCw, SlidersHorizontal, X, ArrowUpDown,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { api, type UsageRecord, type HistoryPage, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

const PROVIDER_COLORS: Record<string, string> = {
  openai:    "#10a37f",
  anthropic: "#d4622a",
  google:    "#4285f4",
  deepseek:  "#5c67f2",
  ollama:    "#22c55e",
};

const PROVIDERS = ["openai", "anthropic", "google", "deepseek", "ollama"];
const PAGE_SIZES = [25, 50, 100];

function fmt_cost(v: number) {
  if (v === 0) return "$0.000000";
  if (v < 0.0001) return `$${v.toExponential(2)}`;
  return `$${v.toFixed(6)}`;
}

function fmt_tokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmt_date(iso: string) {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    time: d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }),
  };
}

function ProviderBadge({ provider }: { provider: string }) {
  const color = PROVIDER_COLORS[provider] ?? "#64748b";
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10px] font-600 uppercase tracking-wider px-2 py-0.5 rounded-full"
      style={{ background: `${color}18`, color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 4px ${color}` }} />
      {provider}
    </span>
  );
}

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-white/5", className)} />;
}

function TableSkeleton() {
  return (
    <div className="divide-y divide-[--border]">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-3.5">
          <Skeleton className="w-24 h-8" />
          <Skeleton className="w-32 h-4 flex-1" />
          <Skeleton className="w-20 h-5" />
          <Skeleton className="w-28 h-4" />
          <Skeleton className="w-16 h-4" />
          <Skeleton className="w-16 h-4" />
          <Skeleton className="w-20 h-4" />
        </div>
      ))}
    </div>
  );
}

function exportCSV(items: UsageRecord[]) {
  const header = ["id", "time", "project", "provider", "model", "tokens_in", "tokens_out", "cost_usd"];
  const rows = items.map((r) => [
    r.id,
    r.created_at,
    r.project_name,
    r.provider,
    r.model,
    r.tokens_in,
    r.tokens_out,
    r.cost_usd,
  ]);
  const csv = [header, ...rows].map((row) => row.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `budgetforge-history-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ActivityPage() {
  const [data, setData]           = useState<HistoryPage | null>(null);
  const [projects, setProjects]   = useState<Project[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef               = useRef<ReturnType<typeof setInterval> | null>(null);

  // filters
  const [page, setPage]           = useState(1);
  const [pageSize, setPageSize]   = useState(50);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [provider, setProvider]   = useState<string | null>(null);
  const [model, setModel]         = useState("");
  const [dateFrom, setDateFrom]   = useState("");
  const [dateTo, setDateTo]       = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const hasActiveFilters = projectId !== null || provider !== null || model || dateFrom || dateTo;

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const result = await api.usage.history({
        page,
        page_size: pageSize,
        project_id: projectId,
        provider,
        model: model || null,
        date_from: dateFrom || null,
        date_to: dateTo || null,
      });
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [page, pageSize, projectId, provider, model, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.projects.list().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => load(true), 5000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, load]);

  function clearFilters() {
    setProjectId(null);
    setProvider(null);
    setModel("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  return (
    <Shell>
      <div className="p-6 max-w-7xl">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start justify-between mb-6"
        >
          <div>
            <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">Activity</h1>
            <p className="text-[--muted-fg] text-sm">Complete history of proxied LLM calls</p>
          </div>
          <div className="flex items-center gap-2">
            {/* Auto-refresh toggle */}
            <button
              onClick={() => setAutoRefresh((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 text-xs font-600 px-3 py-2 rounded-md border cursor-pointer transition-all",
                autoRefresh
                  ? "border-[--amber] text-[--amber] bg-[--amber-dim] shadow-[0_0_12px_rgba(245,158,11,0.2)]"
                  : "border-[--border] text-[--foreground] bg-[--muted] hover:border-[--amber] hover:text-[--amber]"
              )}
              title="Auto-refresh every 5s"
            >
              <RefreshCw className={cn("w-3.5 h-3.5", autoRefresh && "animate-spin")} />
              Live
            </button>
            {/* Filters toggle */}
            <button
              onClick={() => setShowFilters((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 text-xs font-600 px-3 py-2 rounded-md border cursor-pointer transition-all",
                showFilters || hasActiveFilters
                  ? "border-[--amber] text-[--amber] bg-[--amber-dim] shadow-[0_0_12px_rgba(245,158,11,0.2)]"
                  : "border-[--border] text-[--foreground] bg-[--muted] hover:border-[--amber] hover:text-[--amber]"
              )}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              Filters
              {hasActiveFilters && (
                <span className="w-1.5 h-1.5 rounded-full bg-[--amber] shadow-[0_0_4px_rgba(245,158,11,0.8)]" />
              )}
            </button>
            {/* Export */}
            <a
              href={api.usage.exportUrl({ format: "csv", ...(projectId != null ? { project_id: projectId } : {}) })}
              className="flex items-center gap-1.5 text-xs font-600 px-3 py-2 rounded-md border border-[--border] text-[--foreground] bg-[--muted] hover:border-[--amber] hover:text-[--amber] transition-all cursor-pointer"
              download
            >
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </a>
          </div>
        </motion.div>

        {/* Stats bar */}
        {data && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid grid-cols-3 gap-3 mb-4"
          >
            {[
              { label: "Total calls", value: data.total.toLocaleString() },
              { label: "Total cost", value: fmt_cost(data.total_cost_usd) },
              { label: "Showing page", value: `${data.page} / ${data.pages || 1}` },
            ].map(({ label, value }) => (
              <div key={label} className="card-base px-4 py-3 flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-widest text-[--muted-fg] font-600">{label}</span>
                <span className="font-mono text-sm font-600 text-[--foreground]">{value}</span>
              </div>
            ))}
          </motion.div>
        )}

        {/* Filter panel */}
        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden mb-4"
            >
              <div className="card-base p-4 flex flex-wrap gap-4 items-end">
                {/* Project */}
                <div className="flex flex-col gap-1.5 min-w-[180px]">
                  <label className="text-[10px] uppercase tracking-widest text-[--muted-fg] font-600">Project</label>
                  <select
                    value={projectId ?? ""}
                    onChange={(e) => { setProjectId(e.target.value ? Number(e.target.value) : null); setPage(1); }}
                    className="bg-[--muted] border border-[--border] rounded-md px-3 py-2 text-xs text-[--foreground] focus:outline-none focus:border-[--amber]/60"
                  >
                    <option value="">All projects</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>

                {/* Provider chips */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] uppercase tracking-widest text-[--muted-fg] font-600">Provider</label>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => { setProvider(null); setPage(1); }}
                      className={cn(
                        "text-[10px] font-600 uppercase tracking-wider px-2.5 py-1 rounded-full border transition-all",
                        provider === null
                          ? "border-[--amber] text-[--amber] bg-[--amber-dim]"
                          : "border-[--border] text-[--muted-fg] hover:border-[--amber]/40"
                      )}
                    >All</button>
                    {PROVIDERS.map((pv) => {
                      const color = PROVIDER_COLORS[pv];
                      const active = provider === pv;
                      return (
                        <button
                          key={pv}
                          onClick={() => { setProvider(active ? null : pv); setPage(1); }}
                          className="text-[10px] font-600 uppercase tracking-wider px-2.5 py-1 rounded-full border transition-all"
                          style={active
                            ? { borderColor: color, color, background: `${color}18` }
                            : { borderColor: "var(--border)", color: "var(--muted-fg)" }
                          }
                        >{pv}</button>
                      );
                    })}
                  </div>
                </div>

                {/* Model */}
                <div className="flex flex-col gap-1.5 min-w-[160px]">
                  <label className="text-[10px] uppercase tracking-widest text-[--muted-fg] font-600">Model</label>
                  <input
                    type="text"
                    placeholder="e.g. gpt-4o"
                    value={model}
                    onChange={(e) => { setModel(e.target.value); setPage(1); }}
                    className="bg-[--muted] border border-[--border] rounded-md px-3 py-2 text-xs text-[--foreground] placeholder:text-[--muted-fg] focus:outline-none focus:border-[--amber]/60"
                  />
                </div>

                {/* Date range */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] uppercase tracking-widest text-[--muted-fg] font-600">Date range</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="date"
                      value={dateFrom}
                      onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                      className="bg-[--muted] border border-[--border] rounded-md px-3 py-2 text-xs text-[--foreground] focus:outline-none focus:border-[--amber]/60"
                    />
                    <span className="text-[--muted-fg] text-xs">→</span>
                    <input
                      type="date"
                      value={dateTo}
                      onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                      className="bg-[--muted] border border-[--border] rounded-md px-3 py-2 text-xs text-[--foreground] focus:outline-none focus:border-[--amber]/60"
                    />
                  </div>
                </div>

                {/* Clear */}
                {hasActiveFilters && (
                  <button
                    onClick={clearFilters}
                    className="flex items-center gap-1.5 text-xs text-red-400/70 hover:text-red-400 transition-colors pb-0.5"
                  >
                    <X className="w-3 h-3" /> Clear all
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Table */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="card-base overflow-hidden"
        >
          {/* Table header */}
          <div className="grid grid-cols-[140px_1fr_110px_160px_90px_90px_110px] gap-0 px-5 py-2.5 border-b border-[--border] bg-white/[0.02]">
            {[
              { label: "Time" },
              { label: "Project" },
              { label: "Provider" },
              { label: "Model" },
              { label: "Tok. in", mono: true },
              { label: "Tok. out", mono: true },
              { label: "Cost", mono: true },
            ].map(({ label, mono }) => (
              <div
                key={label}
                className={cn(
                  "flex items-center gap-1 text-[10px] uppercase tracking-widest font-600 text-[--muted-fg] whitespace-nowrap",
                  mono && "justify-end"
                )}
              >
                {label}
                <ArrowUpDown className="w-2.5 h-2.5 opacity-30 shrink-0" />
              </div>
            ))}
          </div>

          {/* Rows */}
          {loading ? (
            <TableSkeleton />
          ) : error ? (
            <div className="py-16 text-center">
              <p className="text-sm text-red-400">{error}</p>
              <button onClick={() => load()} className="mt-2 text-xs text-[--amber] hover:underline">Retry</button>
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="py-16 text-center flex flex-col items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[--amber-dim] flex items-center justify-center">
                <Activity className="w-5 h-5 text-[--amber]" />
              </div>
              <p className="text-sm text-[--muted-fg]">
                {hasActiveFilters ? "No calls match the current filters." : "No calls recorded yet."}
              </p>
              {hasActiveFilters && (
                <button onClick={clearFilters} className="text-xs text-[--amber] hover:underline">Clear filters</button>
              )}
            </div>
          ) : (
            <div className="divide-y divide-[--border]">
              {data.items.map((row, i) => {
                const { date, time } = fmt_date(row.created_at);
                const color = PROVIDER_COLORS[row.provider] ?? "#64748b";
                return (
                  <motion.div
                    key={row.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.015, duration: 0.2 }}
                    className="grid grid-cols-[140px_1fr_110px_160px_90px_90px_110px] gap-0 px-5 py-3 hover:bg-white/[0.02] transition-colors group"
                    style={{ borderLeft: `2px solid ${color}18` }}
                  >
                    {/* Time */}
                    <div className="flex flex-col justify-center">
                      <span className="font-mono text-[10px] text-[--foreground]">{time}</span>
                      <span className="font-mono text-[10px] text-[--muted-fg]">{date}</span>
                    </div>

                    {/* Project */}
                    <div className="flex items-center min-w-0 pr-4">
                      <span className="text-xs text-[--foreground] truncate">{row.project_name}</span>
                    </div>

                    {/* Provider */}
                    <div className="flex items-center">
                      <ProviderBadge provider={row.provider} />
                    </div>

                    {/* Model */}
                    <div className="flex items-center pr-4">
                      <span className="font-mono text-[11px] text-[--muted-fg] truncate">{row.model}</span>
                    </div>

                    {/* Tokens in */}
                    <div className="flex items-center justify-end">
                      <span className="font-mono text-xs text-[--muted-fg]">{fmt_tokens(row.tokens_in)}</span>
                    </div>

                    {/* Tokens out */}
                    <div className="flex items-center justify-end">
                      <span className="font-mono text-xs text-[--muted-fg]">{fmt_tokens(row.tokens_out)}</span>
                    </div>

                    {/* Cost */}
                    <div className="flex items-center justify-end">
                      <span
                        className={cn(
                          "font-mono text-xs font-600",
                          row.cost_usd === 0 ? "text-green-400" : "text-[--amber]"
                        )}
                      >
                        {fmt_cost(row.cost_usd)}
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Pagination footer */}
          {data && data.total > 0 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-[--border] bg-white/[0.01]">
              <div className="flex items-center gap-3">
                <span className="text-xs text-[--muted-fg]">
                  {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, data.total)} of {data.total.toLocaleString()}
                </span>
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                  className="bg-[--muted] border border-[--border] rounded px-2 py-1 text-xs text-[--foreground] focus:outline-none"
                >
                  {PAGE_SIZES.map((s) => (
                    <option key={s} value={s}>{s} / page</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(1)}
                  disabled={page === 1}
                  className="px-2 py-1 text-xs text-[--muted-fg] hover:text-[--foreground] disabled:opacity-30 transition-colors"
                >«</button>
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="flex items-center gap-0.5 px-2 py-1 text-xs text-[--muted-fg] hover:text-[--foreground] disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="w-3 h-3" /> Prev
                </button>

                {/* Page numbers */}
                <div className="flex items-center gap-1 mx-1">
                  {Array.from({ length: Math.min(data.pages, 7) }, (_, i) => {
                    let p: number;
                    if (data.pages <= 7) {
                      p = i + 1;
                    } else if (page <= 4) {
                      p = i + 1;
                    } else if (page >= data.pages - 3) {
                      p = data.pages - 6 + i;
                    } else {
                      p = page - 3 + i;
                    }
                    return (
                      <button
                        key={p}
                        onClick={() => setPage(p)}
                        className={cn(
                          "w-7 h-7 text-xs rounded transition-all",
                          p === page
                            ? "bg-[--amber] text-[#070a0f] font-600"
                            : "text-[--muted-fg] hover:text-[--foreground] hover:bg-white/5"
                        )}
                      >{p}</button>
                    );
                  })}
                </div>

                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page === data.pages}
                  className="flex items-center gap-0.5 px-2 py-1 text-xs text-[--muted-fg] hover:text-[--foreground] disabled:opacity-30 transition-colors"
                >
                  Next <ChevronRight className="w-3 h-3" />
                </button>
                <button
                  onClick={() => setPage(data.pages)}
                  disabled={page === data.pages}
                  className="px-2 py-1 text-xs text-[--muted-fg] hover:text-[--foreground] disabled:opacity-30 transition-colors"
                >»</button>
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </Shell>
  );
}
