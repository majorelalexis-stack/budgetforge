"use client";
import { useEffect, useState, FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

type Project = {
  id: number;
  name: string;
  api_key: string;
  plan: string;
  created_at: string | null;
};

type DailySpend = { date: string; spend: number };

function useUsage(projectId: number): DailySpend[] | null {
  const [data, setData] = useState<DailySpend[] | null>(null);
  useEffect(() => {
    fetch(`/api/portal/usage?project_id=${projectId}`, { credentials: "include" })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => setData(d.daily))
      .catch(() => setData([]));
  }, [projectId]);
  return data;
}

function formatDay(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function UsageChart({ projectId }: { projectId: number }) {
  const daily = useUsage(projectId);
  if (!daily) return <div className="h-[120px] flex items-center justify-center text-xs" style={{ color: "#c8d8e8" }}>Loading…</div>;

  const hasData = daily.some((d) => d.spend > 0);
  const chartData = daily.map((d) => ({ ...d, label: formatDay(d.date) }));

  return (
    <div className="mt-4">
      <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "#c8d8e8" }}>
        Usage — last 30 days
      </p>
      {hasData ? (
        <ResponsiveContainer width="100%" height={120}>
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fill: "#c8d8e8" }}
              tickLine={false}
              axisLine={false}
              interval={6}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "#c8d8e8" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `$${v.toFixed(3)}`}
            />
            <Tooltip
              contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11 }}
              formatter={(v) => [`$${Number(v).toFixed(4)}`, "Spend"]}
              labelStyle={{ color: "#c8d8e8" }}
            />
            <Area
              type="monotone"
              dataKey="spend"
              stroke="#f59e0b"
              fill="#f59e0b"
              fillOpacity={0.15}
              strokeWidth={1.5}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-xs text-center py-8" style={{ color: "#c8d8e8" }}>No usage in the last 30 days</p>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="text-xs px-2 py-1 rounded transition-colors"
      style={{ border: "1px solid var(--border)", color: copied ? "#4ade80" : "var(--amber)" }}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function PortalContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (token) {
      // magic link → verify + pose le cookie session 90j
      fetch(`/api/portal/verify?token=${token}`)
        .then((r) => r.ok ? r.json() : Promise.reject(r.status))
        .then((data) => setProjects(data.projects))
        .catch(() => setError("This link is invalid or has expired. Request a new one below."))
        .finally(() => setChecking(false));
    } else {
      // pas de token → essayer le cookie session existant (pas de token disponible)
      fetch("/api/portal/session", { credentials: "include" })
        .then((r) => r.ok ? r.json() : Promise.reject())
        .then((data) => setProjects(data.projects))
        .catch(() => {})
        .finally(() => setChecking(false));
    }
  }, [token]);

  async function handleRequest(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    await fetch("/api/portal/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    setSent(true);
    setLoading(false);
  }

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

  if (checking) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="w-2 h-2 rounded-full"
              style={{ background: "var(--amber)", opacity: 0.6 }} />
          ))}
        </div>
      </div>
    );
  }

  if (projects) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16">
        <h1 className="text-2xl font-bold mb-2">Your projects</h1>
        <p className="text-sm mb-8" style={{ color: "#c8d8e8" }}>
          {projects[0]?.name}
        </p>
        <div className="flex flex-col gap-4">
          {projects.map((p) => (
            <div key={p.id} className="rounded-xl p-5" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
              <div className="flex items-center justify-between mb-3">
                <span className="font-semibold text-sm">{p.name}</span>
                <span className="text-xs px-2 py-0.5 rounded-full font-semibold capitalize"
                  style={{ background: "var(--amber-dim)", color: "var(--amber)" }}>
                  {p.plan}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                <div>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#c8d8e8" }}>BudgetForge key</p>
                  <div className="flex items-center gap-2 bg-black/30 rounded-md px-3 py-2">
                    <code className="font-mono text-xs text-[--amber] flex-1 break-all">{p.api_key}</code>
                    <CopyButton text={p.api_key} />
                  </div>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#c8d8e8" }}>Proxy URL (OpenAI)</p>
                  <div className="flex items-center gap-2 bg-black/30 rounded-md px-3 py-2">
                    <code className="font-mono text-xs text-[--amber] flex-1 break-all">
                      {API_BASE}/proxy/openai/v1
                    </code>
                    <CopyButton text={`${API_BASE}/proxy/openai/v1`} />
                  </div>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#c8d8e8" }}>Proxy URL (Ollama)</p>
                  <div className="flex items-center gap-2 bg-black/30 rounded-md px-3 py-2">
                    <code className="font-mono text-xs text-[--amber] flex-1 break-all">
                      {API_BASE}/proxy/ollama/v1/chat/completions
                    </code>
                    <CopyButton text={`${API_BASE}/proxy/ollama/v1/chat/completions`} />
                  </div>
                </div>
              </div>
              <UsageChart projectId={p.id} />
              <p className="text-[10px] mt-3" style={{ color: "#c8d8e8" }}>
                Add header <code className="text-[--amber]">X-Provider-Key: your-openai-key</code> to each request.
                Ollama routes require no provider key — local inference is always free.
              </p>
            </div>
          ))}
        </div>
        {projects.length === 0 && (
          <p style={{ color: "#c8d8e8" }}>No projects found for this email.</p>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto px-6 py-16">
      <h1 className="text-2xl font-bold mb-2">Access your keys</h1>
      <p className="text-sm mb-8" style={{ color: "#c8d8e8" }}>
        {error ? (
          <span style={{ color: "#ef4444" }}>{error}</span>
        ) : (
          "Enter your email — we'll send you a secure link to see your projects and API keys."
        )}
      </p>
      {sent ? (
        <div className="rounded-xl p-6 text-center" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
          <p className="text-lg font-semibold mb-2">Check your inbox</p>
          <p className="text-sm" style={{ color: "#c8d8e8" }}>
            A magic link has been sent to <strong>{email}</strong>. It expires in 1 hour.
          </p>
        </div>
      ) : (
        <form onSubmit={handleRequest} className="flex flex-col gap-4">
          <input
            type="email"
            required
            placeholder="your@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-3 rounded-lg text-sm outline-none"
            style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--foreground)" }}
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90 disabled:opacity-50"
            style={{ background: "var(--amber)", color: "#000" }}
          >
            {loading ? "Sending…" : "Send magic link →"}
          </button>
        </form>
      )}
    </div>
  );
}

export default function PortalPage() {
  return (
    <div className="min-h-screen" style={{ background: "var(--background)", color: "var(--foreground)" }}>
      <nav className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border)" }}>
        <a href="/" className="font-bold text-lg tracking-tight">
          LLM <span style={{ color: "var(--amber)" }}>BudgetForge</span>
        </a>
      </nav>
      <Suspense>
        <PortalContent />
      </Suspense>
    </div>
  );
}
