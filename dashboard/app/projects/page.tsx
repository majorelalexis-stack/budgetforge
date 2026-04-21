"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, Trash2, Settings2, ArrowRight, Shield,
  AlertTriangle, CheckCircle, XCircle, ChevronDown,
} from "lucide-react";
import Link from "next/link";
import { Shell } from "@/components/shell";
import { BurnBar } from "@/components/burn-bar";
import { Toast } from "@/components/toast";
import { api, type Project, type UsageSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ProjectWithUsage extends Project { usage: UsageSummary | null }

function StatusDot({ pct }: { pct: number }) {
  const color =
    pct >= 100 ? "#ef4444" :
    pct >= 80  ? "#f59e0b" : "#22c55e";
  return (
    <span
      className="inline-block w-2 h-2 rounded-full"
      style={{
        background: color,
        boxShadow: `0 0 8px ${color}`,
      }}
    />
  );
}

function CreateProjectModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Project name is required");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await onCreate(name.trim());
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error creating project");
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="card-base w-full max-w-sm p-6"
      >
        <h2 className="font-heading font-700 text-lg mb-1">New Project</h2>
        <p className="text-xs text-[--muted-fg] mb-5">
          A project groups API calls under a shared budget.
        </p>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div>
            <label className="text-xs text-[--muted-fg] block mb-1.5">Project name</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => { setName(e.target.value); setError(""); }}
              placeholder="e.g. prod-chatbot"
              className={cn(
                "w-full bg-[--muted] border border-[--border] rounded-md px-3 py-2",
                "text-sm text-[--foreground] font-mono placeholder:text-[--muted-fg]",
                "focus:outline-none focus:border-[--amber] transition-colors"
              )}
            />
            {error && <p className="text-xs text-red-400 mt-1.5">{error}</p>}
          </div>
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-md text-sm text-[--muted-fg] hover:text-[--foreground] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="btn-amber"
            >
              {loading ? (
                <span className="w-4 h-4 rounded-full border-2 border-[#070a0f]/40 border-t-[#070a0f] animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              Create
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectWithUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [toast, setToast] = useState<{ show: boolean; message: string }>({ show: false, message: "" });
  function showToast(message: string) { setToast({ show: true, message }); }

  async function refresh() {
    try {
      const list = await api.projects.list();
      const withUsage = await Promise.all(
        list.map(async (p) => {
          const usage = p.budget_usd != null
            ? await api.projects.usage(p.id).catch(() => null)
            : null;
          return { ...p, usage };
        })
      );
      setProjects(withUsage);
    } catch { /* offline */ }
    finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, []);

  async function handleCreate(name: string) {
    const created = await api.projects.create(name);
    setProjects((prev) => [...prev, { ...created, usage: null }]);
    showToast(`Project "${name}" created`);
    refresh();
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this project and all its usage history?")) return;
    await api.projects.delete(id);
    await refresh();
  }

  return (
    <Shell>
      <div className="p-6 max-w-5xl">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center justify-between mb-8"
        >
          <div>
            <h1 className="font-heading font-800 text-2xl tracking-tight mb-1">Projects</h1>
            <p className="text-[--muted-fg] text-sm">Manage projects and their LLM budgets</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="btn-amber"
          >
            <Plus className="w-4 h-4" />
            New project
          </button>
        </motion.div>

        {/* Projects grid */}
        {loading ? (
          <div className="flex items-center justify-center py-24">
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
        ) : projects.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="card-base flex flex-col items-center justify-center py-20 gap-4"
          >
            <div className="w-12 h-12 rounded-xl bg-[--amber-dim] flex items-center justify-center">
              <Shield className="w-6 h-6 text-[--amber]" />
            </div>
            <div className="text-center">
              <p className="font-heading font-700 text-base mb-1">No projects yet</p>
              <p className="text-[--muted-fg] text-sm">Create your first project to start tracking LLM spend</p>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="btn-amber"
            >
              <Plus className="w-4 h-4" /> Create project
            </button>
          </motion.div>
        ) : (
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
            className="grid gap-4 md:grid-cols-2"
          >
            {projects.map((p) => {
              const pct = p.usage?.pct_used ?? 0;
              const hasBudget = p.budget_usd != null;
              return (
                <motion.div
                  key={p.id}
                  variants={{
                    hidden: { opacity: 0, y: 14 },
                    show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as [number,number,number,number] } },
                  }}
                  className="card-base p-5 flex flex-col gap-4 group"
                >
                  {/* Top row */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <StatusDot pct={pct} />
                      <div className="min-w-0">
                        <h3 className="font-heading font-700 text-sm text-[--foreground] truncate">{p.name}</h3>
                        <p className="font-mono text-[10px] text-[--muted-fg] truncate mt-0.5">{p.api_key}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Link
                        href={`/projects/${p.id}`}
                        className="p-1.5 rounded-md text-[--muted-fg] hover:text-[--amber] hover:bg-[--amber-dim] transition-all"
                        title="Configure"
                      >
                        <Settings2 className="w-3.5 h-3.5" />
                      </Link>
                      <button
                        onClick={() => handleDelete(p.id)}
                        className="p-1.5 rounded-md text-[--muted-fg] hover:text-red-400 hover:bg-red-500/10 transition-all"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Budget info */}
                  {hasBudget ? (
                    <div className="flex flex-col gap-2">
                      <BurnBar pct={pct} height={5} />
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs text-[--muted-fg]">
                          ${(p.usage?.used_usd ?? 0).toFixed(4)} used
                        </span>
                        <span className="font-mono text-xs text-[--muted-fg]">
                          ${p.budget_usd!.toFixed(2)} budget
                        </span>
                      </div>
                    </div>
                  ) : (
                    <Link
                      href={`/projects/${p.id}`}
                      className="flex items-center gap-1.5 text-xs text-[--amber] hover:opacity-80 transition-opacity"
                    >
                      <AlertTriangle className="w-3 h-3" /> Set a budget →
                    </Link>
                  )}

                  {/* Action + CTA */}
                  <div className="flex items-center justify-between pt-2 border-t border-[--border]">
                    <div className="flex items-center gap-2">
                      {p.action && (
                        <span className={cn(
                          "text-[10px] font-600 uppercase tracking-wider px-2 py-0.5 rounded-full",
                          p.action === "block"     && "bg-red-500/10 text-red-400",
                          p.action === "downgrade" && "bg-blue-500/10 text-blue-400",
                        )}>
                          {p.action}
                        </span>
                      )}
                      {p.alert_threshold_pct != null && (
                        <span className="text-[10px] text-[--muted-fg]">
                          Alert at {p.alert_threshold_pct}%
                        </span>
                      )}
                    </div>
                    <Link
                      href={`/projects/${p.id}`}
                      className="flex items-center gap-1 text-xs text-[--muted-fg] hover:text-[--amber] transition-colors"
                    >
                      Details <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </div>

      {/* Create modal */}
      <AnimatePresence>
        {showCreate && (
          <CreateProjectModal
            onClose={() => setShowCreate(false)}
            onCreate={handleCreate}
          />
        )}
      </AnimatePresence>

      {/* Toast — P3.3 */}
      <Toast
        show={toast.show}
        message={toast.message}
        onClose={() => setToast({ show: false, message: "" })}
      />
    </Shell>
  );
}
