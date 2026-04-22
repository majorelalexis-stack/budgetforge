"use client";
import { useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

function StripeLogo() {
  return (
    <svg role="img" aria-label="Stripe" viewBox="0 0 60 25" width="48" height="20">
      <text
        x="0"
        y="19"
        fontFamily="system-ui, -apple-system, sans-serif"
        fontWeight="700"
        fontSize="20"
        fill="#635bff"
      >
        Stripe
      </text>
    </svg>
  );
}

type Plan = {
  id: "free" | "pro" | "agency";
  name: string;
  price: string;
  period: string;
  calls: string;
  projects: string;
  features: readonly string[];
  cta: string;
  highlight: boolean;
};

const PLANS: readonly Plan[] = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    period: "forever",
    calls: "1,000 calls / month",
    projects: "1 project",
    features: [
      "Hard budget limits",
      "Email alerts",
      "Usage export (CSV/JSON)",
      "OpenAI + Anthropic + Ollama (local)",
    ],
    cta: "Try Free",
    highlight: false,
  },
  {
    id: "pro",
    name: "Pro",
    price: "$29",
    period: "/month",
    calls: "100,000 calls / month",
    projects: "10 projects",
    features: [
      "All Free features",
      "OpenAI · Anthropic · Google · DeepSeek · Ollama (local)",
      "Webhooks (Slack, custom)",
      "Auto-downgrade chains",
      "Team members",
    ],
    cta: "Get Pro",
    highlight: true,
  },
  {
    id: "agency",
    name: "Agency",
    price: "$79",
    period: "/month",
    calls: "500,000 calls / month",
    projects: "Unlimited projects",
    features: [
      "All Pro features incl. Ollama (local)",
      "Custom rate limits per project",
      "White-label proxy URL",
      "Dedicated support SLA",
      "Per-agent budget tracking",
    ],
    cta: "Get Agency",
    highlight: false,
  },
] as const;

const PROVIDERS: readonly string[] = ["OpenAI", "Anthropic", "Google", "DeepSeek", "Ollama"];

export function PricingSection() {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [billing, setBilling] = useState<"monthly" | "annual">("monthly");

  async function handleCheckout(planId: Plan["id"]) {
    setLoading(planId);
    setError(null);
    try {
      const resp = await fetch(`/api/checkout/${planId}`, { method: "POST" });
      if (!resp.ok) throw new Error("checkout_failed");
      const { checkout_url } = await resp.json();
      window.location.href = checkout_url;
    } catch {
      setError("Could not start checkout — please try again or contact support.");
      setLoading(null);
    }
  }

  return (
    <section id="pricing" className="max-w-4xl mx-auto px-6 pb-20">
      <h2 className="text-center text-2xl font-bold mb-3">Simple pricing</h2>
      <p className="text-center text-sm mb-8" style={{ color: "#c8d8e8" }}>
        One flat price. Full control over your LLM spend.
      </p>

      <div className="flex justify-center mb-10" role="group" aria-label="Billing frequency">
        <div
          className="inline-flex rounded-full p-1"
          style={{ border: "1px solid var(--border)", background: "var(--card)" }}
        >
          <button
            type="button"
            onClick={() => setBilling("monthly")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold transition-colors"
            style={
              billing === "monthly"
                ? { background: "var(--amber)", color: "#000" }
                : { color: "#c8d8e8" }
            }
          >
            Monthly
          </button>
          <button
            type="button"
            disabled
            onClick={() => setBilling("annual")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold transition-colors opacity-50 cursor-not-allowed"
            style={{ color: "#c8d8e8" }}
            title="Annual billing — coming soon"
          >
            Annual — save 20% (coming soon)
          </button>
        </div>
      </div>

      {error && (
        <p className="text-center text-sm mb-6" style={{ color: "#ef4444" }}>
          {error}
        </p>
      )}

      <div className="grid sm:grid-cols-3 gap-5">
        {PLANS.map((plan) => (
          <div
            key={plan.id}
            className="rounded-xl p-6 flex flex-col relative"
            style={{
              border: plan.highlight ? "2px solid var(--amber)" : "1px solid var(--border)",
              background: "var(--card)",
            }}
          >
            {plan.highlight && (
              <div
                className="absolute -top-3 left-1/2 -translate-x-1/2 text-xs font-semibold px-3 py-1 rounded-full whitespace-nowrap"
                style={{ background: "var(--amber)", color: "#000" }}
              >
                Most popular
              </div>
            )}

            <div className="mb-4">
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#c8d8e8" }}>
                {plan.name}
              </p>
              <p className="text-3xl font-bold mt-1">
                {plan.price}
                <span className="text-lg font-medium ml-1" style={{ color: "var(--foreground)" }}>
                  {plan.period}
                </span>
              </p>
            </div>

            <div className="text-sm font-medium mb-4 space-y-0.5" style={{ color: "var(--amber)" }}>
              <p>{plan.calls}</p>
              <p>{plan.projects}</p>
            </div>

            <ul className="text-sm space-y-2 mb-6 flex-1" style={{ color: "#c8d8e8" }}>
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <span style={{ color: "#4ade80" }}>✓</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>

            {plan.id === "free" ? (
              <Link
                href="/portal"
                className="w-full py-2.5 rounded-lg font-semibold text-sm text-center transition-opacity hover:opacity-90"
                style={{ border: "1px solid var(--border)", background: "transparent", color: "var(--foreground)" }}
              >
                {plan.cta} →
              </Link>
            ) : (
              <button
                onClick={() => handleCheckout(plan.id)}
                disabled={loading === plan.id}
                className="w-full py-2.5 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90 disabled:opacity-70 cursor-pointer flex items-center justify-center gap-2"
                style={
                  plan.highlight
                    ? { background: "var(--amber)", color: "#000" }
                    : { border: "1px solid var(--border)", background: "transparent", color: "var(--foreground)" }
                }
              >
                {loading === plan.id ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{plan.cta}</span>
                  </>
                ) : (
                  <span>{plan.cta} →</span>
                )}
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-col items-center gap-4 mt-10">
        <p className="text-xs" style={{ color: "#c8d8e8" }}>
          Cancel anytime. Payments secured by Stripe.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3 opacity-80">
          <StripeLogo />
          <span className="text-xs" style={{ color: "#c8d8e8" }}>·</span>
          {PROVIDERS.map((name) => (
            <span
              key={name}
              className="text-xs font-medium px-2.5 py-1 rounded-full"
              style={{ border: "1px solid var(--border)", color: "#c8d8e8" }}
            >
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
