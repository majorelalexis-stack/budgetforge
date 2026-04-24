"use client";

import Link from "next/link";
import { BurnBar } from "@/components/burn-bar";
import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";

const DEMO_PROJECTS = [
  { slug: "ai-chat-assistant",  name: "AI Chat Assistant",   budget: 150,  used: 108.45, action: "downgrade", providers: ["anthropic", "ollama"] },
  { slug: "content-generator",  name: "Content Generator",   budget: 300,  used: 287.92, action: "block",     providers: ["openai", "anthropic"] },
  { slug: "web-scraper-agent",  name: "Web Scraper Agent",   budget: 75,   used: 22.1,   action: "downgrade", providers: ["openai"] },
  { slug: "image-analysis",     name: "Image Analysis",      budget: 200,  used: 156.33, action: "downgrade", providers: ["google", "anthropic"] },
  { slug: "code-review-bot",    name: "Code Review Bot",     budget: 100,  used: 38.67,  action: "block",     providers: ["anthropic", "openai"] },
];

function StatusIcon({ pct }: { pct: number }) {
  if (pct >= 100) return <XCircle className="w-4 h-4 text-red-400" />;
  if (pct >= 80)  return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <CheckCircle className="w-4 h-4 text-green-400" />;
}

export default function DemoProjectsPage() {
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

        <div className="divide-y" style={{ borderColor: "var(--border)" }}>
          {DEMO_PROJECTS.map((p) => {
            const pct = Math.min(100, (p.used / p.budget) * 100);
            return (
              <Link key={p.slug} href={`/demo/projects/${p.slug}`}>
                <div className="grid grid-cols-[auto_1fr_140px_120px_100px] gap-4 items-center px-5 py-4 hover:bg-white/5 transition-colors cursor-pointer">
                  <StatusIcon pct={pct} />
                  <div>
                    <p className="font-medium text-sm">{p.name}</p>
                    <p className="text-xs mt-0.5" style={{ color: "var(--muted-fg)" }}>
                      {p.providers.join(", ")} · {pct.toFixed(1)}% used
                    </p>
                  </div>
                  <BurnBar pct={pct} showValue={false} height={5} />
                  <div className="text-right">
                    <p className="font-mono text-sm">${p.used.toFixed(2)}</p>
                    <p className="font-mono text-xs" style={{ color: "var(--muted-fg)" }}>/ ${p.budget.toFixed(2)}</p>
                  </div>
                  <div className="text-right">
                    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                      p.action === "block"     ? "bg-red-500/10 text-red-400" :
                      p.action === "downgrade" ? "bg-blue-500/10 text-blue-400" :
                                                 "bg-white/5 text-gray-400"
                    }`}>
                      {p.action}
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      <p className="mt-6 text-center text-sm" style={{ color: "var(--muted-fg)" }}>
        <a href="/" className="underline" style={{ color: "var(--amber)" }}>
          Create your own account to manage real projects →
        </a>
      </p>
    </div>
  );
}
