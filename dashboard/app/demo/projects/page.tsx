"use client";

import { useEffect, useState } from "react";
import { BurnBar } from "@/components/burn-bar";
import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";

interface DemoProject {
  name: string;
  budget_usd: number;
  used_usd: number;
  pct_used: number;
  action: string | null;
  allowed_providers: string[];
}

function StatusIcon({ pct }: { pct: number }) {
  if (pct >= 100) return <XCircle className="w-4 h-4 text-red-400" />;
  if (pct >= 80) return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <CheckCircle className="w-4 h-4 text-green-400" />;
}

export default function DemoProjectsPage() {
  const [projects, setProjects] = useState<DemoProject[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/demo/projects")
      .then((r) => r.json())
      .then((data) => { setProjects(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-bold text-2xl tracking-tight mb-1">Projects</h1>
          <p className="text-sm" style={{ color: "var(--muted-fg)" }}>Demo projects — read only</p>
        </div>
        <span className="text-xs px-3 py-1.5 rounded-lg font-medium" style={{ background: "rgba(245,158,11,0.1)", color: "var(--amber)", border: "1px solid rgba(245,158,11,0.2)" }}>
          Read only — no changes
        </span>
      </div>

      <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
        <div className="grid grid-cols-[auto_1fr_140px_120px_100px] gap-4 px-5 py-3 text-xs font-semibold uppercase tracking-wider border-b" style={{ color: "var(--muted-fg)", borderColor: "var(--border)" }}>
          <span></span>
          <span>Project</span>
          <span>Budget usage</span>
          <span className="text-right">Spent</span>
          <span className="text-right">Action</span>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm" style={{ color: "var(--muted-fg)" }}>Loading…</div>
        ) : (
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {projects.map((p) => (
              <div key={p.name} className="grid grid-cols-[auto_1fr_140px_120px_100px] gap-4 items-center px-5 py-4">
                <StatusIcon pct={p.pct_used} />
                <div>
                  <p className="font-medium text-sm">{p.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--muted-fg)" }}>
                    {p.allowed_providers?.join(", ") ?? "openai"} · {p.pct_used.toFixed(1)}% used
                  </p>
                </div>
                <BurnBar pct={p.pct_used} showValue={false} height={5} />
                <div className="text-right">
                  <p className="font-mono text-sm">${p.used_usd.toFixed(2)}</p>
                  <p className="font-mono text-xs" style={{ color: "var(--muted-fg)" }}>/ ${p.budget_usd.toFixed(2)}</p>
                </div>
                <div className="text-right">
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                    p.action === "block" ? "bg-red-500/10 text-red-400" :
                    p.action === "downgrade" ? "bg-blue-500/10 text-blue-400" :
                    "bg-white/5 text-gray-400"
                  }`}>
                    {p.action ?? "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="mt-6 text-center text-sm" style={{ color: "var(--muted-fg)" }}>
        <a href="https://github.com/majorelalexis-stack/budgetforge" className="underline" style={{ color: "var(--amber)" }}>
          Self-host BudgetForge to create your own projects →
        </a>
      </p>
    </div>
  );
}
