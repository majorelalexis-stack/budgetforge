"use client";

import { useEffect, useState } from "react";

interface DemoLog {
  timestamp: string;
  project: string;
  provider: string;
  model: string;
  tokens: number;
  cost_usd: number;
  status: string;
}

const DEMO_ACTIVITY: DemoLog[] = [
  { timestamp: "2026-04-21 17:42:11", project: "GPT-4 Production API", provider: "openai", model: "gpt-4o", tokens: 2840, cost_usd: 0.0284, status: "blocked" },
  { timestamp: "2026-04-21 17:38:05", project: "Claude Research Agent", provider: "anthropic", model: "claude-3-5-sonnet", tokens: 5120, cost_usd: 0.0768, status: "ok" },
  { timestamp: "2026-04-21 17:31:44", project: "Internal Summariser", provider: "openai", model: "gpt-4o-mini", tokens: 1200, cost_usd: 0.0006, status: "downgraded" },
  { timestamp: "2026-04-21 17:20:02", project: "Slack Bot (Ollama)", provider: "ollama", model: "llama3.2", tokens: 890, cost_usd: 0.0000, status: "ok" },
  { timestamp: "2026-04-21 17:10:55", project: "Claude Research Agent", provider: "anthropic", model: "claude-3-5-sonnet", tokens: 3400, cost_usd: 0.0510, status: "ok" },
  { timestamp: "2026-04-21 16:58:12", project: "GPT-4 Production API", provider: "openai", model: "gpt-4o", tokens: 1980, cost_usd: 0.0198, status: "blocked" },
  { timestamp: "2026-04-21 16:45:30", project: "Internal Summariser", provider: "openai", model: "gpt-4o-mini", tokens: 750, cost_usd: 0.0004, status: "ok" },
  { timestamp: "2026-04-21 16:32:09", project: "Slack Bot (Ollama)", provider: "ollama", model: "llama3.2", tokens: 430, cost_usd: 0.0000, status: "ok" },
  { timestamp: "2026-04-21 16:18:47", project: "Claude Research Agent", provider: "anthropic", model: "claude-3-5-sonnet", tokens: 6200, cost_usd: 0.0930, status: "ok" },
  { timestamp: "2026-04-21 16:05:22", project: "GPT-4 Production API", provider: "openai", model: "gpt-4o", tokens: 3100, cost_usd: 0.0310, status: "blocked" },
  { timestamp: "2026-04-21 15:52:11", project: "Internal Summariser", provider: "openai", model: "gpt-4o-mini", tokens: 920, cost_usd: 0.0005, status: "ok" },
  { timestamp: "2026-04-21 15:38:04", project: "Slack Bot (Ollama)", provider: "ollama", model: "llama3.2", tokens: 1100, cost_usd: 0.0000, status: "ok" },
];

const STATUS_STYLES: Record<string, string> = {
  ok:          "bg-green-500/10 text-green-400",
  blocked:     "bg-red-500/10 text-red-400",
  downgraded:  "bg-blue-500/10 text-blue-400",
};

const PROVIDER_COLORS: Record<string, string> = {
  openai:    "#10a37f",
  anthropic: "#d4622a",
  google:    "#4285f4",
  ollama:    "#22c55e",
};

export default function DemoActivityPage() {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { setLoaded(true); }, []);

  return (
    <div className="p-6 max-w-5xl">
      <div className="mb-8">
        <h1 className="font-bold text-2xl tracking-tight mb-1">Activity</h1>
        <p className="text-sm" style={{ color: "var(--muted-fg)" }}>Recent API calls — demo data, read only</p>
      </div>

      <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
        <div className="grid grid-cols-[160px_1fr_100px_100px_80px_80px] gap-3 px-5 py-3 text-xs font-semibold uppercase tracking-wider border-b" style={{ color: "var(--muted-fg)", borderColor: "var(--border)" }}>
          <span>Time</span>
          <span>Project</span>
          <span>Provider</span>
          <span>Model</span>
          <span className="text-right">Tokens</span>
          <span className="text-right">Status</span>
        </div>

        {!loaded ? (
          <div className="py-12 text-center text-sm" style={{ color: "var(--muted-fg)" }}>Loading…</div>
        ) : (
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {DEMO_ACTIVITY.map((log, i) => (
              <div key={i} className="grid grid-cols-[160px_1fr_100px_100px_80px_80px] gap-3 items-center px-5 py-3">
                <span className="font-mono text-xs" style={{ color: "var(--muted-fg)" }}>{log.timestamp.slice(11)}</span>
                <div>
                  <p className="text-sm font-medium truncate">{log.project}</p>
                  <p className="font-mono text-xs" style={{ color: "var(--muted-fg)" }}>${log.cost_usd.toFixed(4)}</p>
                </div>
                <span className="text-xs font-medium capitalize" style={{ color: PROVIDER_COLORS[log.provider] ?? "var(--muted-fg)" }}>
                  {log.provider}
                </span>
                <span className="font-mono text-xs truncate" style={{ color: "var(--muted-fg)" }}>{log.model}</span>
                <span className="font-mono text-xs text-right">{log.tokens.toLocaleString()}</span>
                <div className="flex justify-end">
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${STATUS_STYLES[log.status] ?? "bg-white/5 text-gray-400"}`}>
                    {log.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
