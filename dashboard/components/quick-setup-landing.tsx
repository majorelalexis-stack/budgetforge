"use client";
import { useState } from "react";
import Link from "next/link";

const TABS = [
  {
    id: "cursor",
    label: "Cursor",
    steps: [
      "Open Cursor → Settings (gear icon, bottom-left) → Models",
      'In the "API Key" field — paste your BudgetForge key (bf-...)',
      'In the "Base URL" field — paste: https://llmbudget.maxiaworld.app/proxy/openai',
      'Click "Add custom header" → Name: X-Provider-Key → Value: your OpenAI key (sk-...)',
      "Click Save. All Cursor AI requests are now tracked and budget-limited.",
    ],
  },
  {
    id: "n8n",
    label: "n8n / Make",
    steps: [
      "Open your AI node (e.g. OpenAI Chat Model) → Credentials",
      'In "API Key" — paste your BudgetForge key (bf-...)',
      'In "Base URL" — paste: https://llmbudget.maxiaworld.app/proxy/openai',
      "Add a header → Name: X-Provider-Key → Value: your real OpenAI key (sk-...)",
      "Save and run. Every call is now tracked and budget-limited.",
    ],
  },
  {
    id: "python",
    label: "Python / JS",
    steps: [
      "Find where you create your OpenAI client in your code",
      "Change api_key to your BudgetForge key (bf-...)",
      "Add base_url pointing to our proxy (see URL below)",
      "Add a default header — X-Provider-Key = your real OpenAI key",
      "Deploy. Every API call is tracked and capped at your budget.",
    ],
  },
  {
    id: "any",
    label: "Any tool",
    steps: [
      "Find the API Key or OpenAI Key setting in your tool",
      "Replace your current provider key with your BudgetForge key (bf-...)",
      "Find the Base URL or Endpoint setting and paste the proxy URL for your provider",
      "Add a custom header → Name: X-Provider-Key → Value: your original provider key",
      "Save. BudgetForge now tracks and limits all your AI spend.",
    ],
  },
] as const;

const PROXY_URLS = [
  { label: "OpenAI", url: "https://llmbudget.maxiaworld.app/proxy/openai/v1" },
  { label: "Anthropic", url: "https://llmbudget.maxiaworld.app/proxy/anthropic/v1" },
  { label: "Google", url: "https://llmbudget.maxiaworld.app/proxy/google/v1" },
  { label: "DeepSeek", url: "https://llmbudget.maxiaworld.app/proxy/deepseek/v1" },
];

export function QuickSetupLanding() {
  const [active, setActive] = useState<string>("cursor");
  const tab = TABS.find((t) => t.id === active)!;

  return (
    <section id="setup" className="max-w-2xl mx-auto px-6 pb-20">
      <h2 className="text-2xl font-bold text-center mb-3">Connect in 2 minutes</h2>
      <p className="text-center text-sm mb-8" style={{ color: "#c8d8e8" }}>
        Pick your tool and follow the steps. Your original provider key stays with you — we never store it.
      </p>

      <div className="rounded-2xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
        <div className="flex" style={{ borderBottom: "1px solid var(--border)", background: "var(--card)" }}>
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActive(t.id)}
              className="flex-1 py-3 text-sm font-medium transition-colors"
              style={{
                color: active === t.id ? "var(--amber)" : "#c8d8e8",
                borderBottom: active === t.id ? "2px solid var(--amber)" : "2px solid transparent",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-6" style={{ background: "var(--card)" }}>
          <ol className="flex flex-col gap-4">
            {tab.steps.map((step, i) => (
              <li key={i} className="flex items-start gap-4">
                <span
                  className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{ background: "var(--amber)", color: "#000" }}
                >
                  {i + 1}
                </span>
                <span className="text-sm leading-relaxed pt-0.5" style={{ color: "var(--foreground)" }}>
                  {step}
                </span>
              </li>
            ))}
          </ol>

          <details className="mt-6 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
            <summary className="text-xs cursor-pointer select-none hover:opacity-80 transition-opacity" style={{ color: "#c8d8e8" }}>
              Proxy URLs for all providers (OpenAI · Anthropic · Google · DeepSeek)
            </summary>
            <div className="mt-3 flex flex-col gap-2">
              {PROXY_URLS.map(({ label, url }) => (
                <div key={label} className="flex items-center gap-3 text-xs">
                  <span className="w-16 shrink-0" style={{ color: "#c8d8e8" }}>{label}</span>
                  <code style={{ color: "var(--amber)" }}>{url}</code>
                </div>
              ))}
            </div>
          </details>

          <p className="text-xs mt-4" style={{ color: "#c8d8e8" }}>
            No key yet?{" "}
            <a href="#hero" style={{ color: "var(--amber)" }} className="hover:opacity-80">
              Get one free above →
            </a>
            {"  ·  "}
            <Link href="/portal" style={{ color: "var(--amber)" }} className="hover:opacity-80">
              Access my keys →
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}
