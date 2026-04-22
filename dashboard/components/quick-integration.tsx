"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { getQuickSetupTabs, PROXY_URLS } from "@/lib/quick-setup-tabs";
import { cn } from "@/lib/utils";

function CopyLine({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2 bg-black/30 rounded-md px-3 py-2">
      <code className="font-mono text-xs text-[--amber] flex-1 break-all">{text}</code>
      <button
        onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
        className="shrink-0 p-1 rounded hover:bg-white/10 transition-colors text-[--muted-fg] hover:text-[--amber]"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}

export function QuickIntegration({ apiKey, proxyBase }: { apiKey: string; proxyBase: string }) {
  const tabs = getQuickSetupTabs(apiKey, proxyBase);
  const [activeTab, setActiveTab] = useState(tabs[0].id);
  const tab = tabs.find((t) => t.id === activeTab)!;

  return (
    <div>
      {/* Tab bar */}
      <div className="flex gap-1.5 mb-5 flex-wrap">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-500 transition-all border",
              activeTab === t.id
                ? "border-transparent text-[#070a0f]"
                : "border-[--border] text-[--muted-fg] hover:border-white/20 bg-transparent"
            )}
            style={activeTab === t.id ? { background: "var(--amber)" } : undefined}
          >
            {t.emoji} {t.label}
          </button>
        ))}
      </div>

      {/* Steps */}
      <div className="flex flex-col gap-3 mb-5">
        {tab.steps.map((step, i) => {
          const clean = step
            .replace(`: ${apiKey}`, "")
            .replace(`: ${tab.url ?? "NOPE"}`, "");
          return (
            <div key={i} className="flex gap-3 items-start">
              <span
                className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-700 shrink-0 mt-0.5"
                style={{ background: "var(--amber-dim)", color: "var(--amber)", border: "1px solid var(--amber-glow)" }}
              >
                {i + 1}
              </span>
              <p className="text-sm leading-relaxed" style={{ color: "#c8d8e8" }}>{clean}</p>
            </div>
          );
        })}
      </div>

      {/* Copy fields */}
      <div className="flex flex-col gap-2 mb-4">
        <div>
          <p className="text-[10px] text-[--muted-fg] mb-1 uppercase tracking-wider">Your BudgetForge key</p>
          <CopyLine text={apiKey} />
        </div>
        {tab.url && (
          <div>
            <p className="text-[10px] text-[--muted-fg] mb-1 uppercase tracking-wider">Proxy URL</p>
            <CopyLine text={tab.url} />
          </div>
        )}
      </div>

      {/* All proxy URLs */}
      <details>
        <summary className="text-[10px] text-[--muted-fg] cursor-pointer hover:text-[--foreground] transition-colors select-none">
          All proxy URLs (OpenAI · Anthropic · Google · DeepSeek · Ollama)
        </summary>
        <div className="mt-2 flex flex-col gap-1.5">
          {Object.entries(PROXY_URLS).map(([provider, path]) => (
            <div key={provider} className="flex items-center gap-2">
              <span className="text-[10px] w-16 shrink-0 capitalize" style={{ color: "#c8d8e8" }}>{provider}</span>
              <CopyLine text={`${proxyBase}${path}`} />
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
