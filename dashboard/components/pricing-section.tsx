"use client";
import { useState } from "react";

const PLANS = [
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
      "OpenAI + Anthropic",
      "Ollama (local LLMs, free)",
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
      "OpenAI · Anthropic · Google · DeepSeek · Ollama",
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
      "All Pro features",
      "Unlimited projects",
      "Per-agent budget tracking",
      "Priority support",
    ],
    cta: "Get Agency",
    highlight: false,
  },
] as const;

export function PricingSection() {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleCheckout(planId: string) {
    if (planId === "free") {
      document.getElementById("hero")?.scrollIntoView({ behavior: "smooth" });
      return;
    }
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
      <p className="text-center text-sm mb-10" style={{ color: "#c8d8e8" }}>
        No seat fees. No per-token charges. Just monthly call quotas.
      </p>

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
                <span className="text-sm font-normal ml-0.5" style={{ color: "#c8d8e8" }}>
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

            <button
              onClick={() => handleCheckout(plan.id)}
              disabled={loading === plan.id}
              className="w-full py-2.5 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90 disabled:opacity-50 cursor-pointer"
              style={
                plan.highlight
                  ? { background: "var(--amber)", color: "#000" }
                  : { border: "1px solid var(--border)", background: "transparent", color: "var(--foreground)" }
              }
            >
              {loading === plan.id ? "Redirecting…" : plan.cta + " →"}
            </button>
          </div>
        ))}
      </div>

      <p className="text-center text-xs mt-6" style={{ color: "#c8d8e8" }}>
        Cancel anytime. Payments secured by Stripe.
      </p>
    </section>
  );
}
