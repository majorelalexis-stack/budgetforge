import Image from "next/image";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--background)", color: "var(--foreground)" }}
    >
      {/* Nav */}
      <nav
        className="px-6 py-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <Image src="/logo.png" alt="BudgetForge" width={36} height={36} className="rounded-lg" />
          <span className="font-bold text-lg tracking-tight">
            LLM <span style={{ color: "var(--amber)" }}>BudgetForge</span>
          </span>
        </div>
        <Link href="/login" className="text-sm hover:underline" style={{ color: "var(--muted-fg)" }}>
          Admin login →
        </Link>
      </nav>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 pt-20 pb-16 text-center">
        <div
          className="inline-block text-xs font-semibold px-3 py-1 rounded-full mb-6"
          style={{ border: "1px solid var(--amber)", color: "var(--amber)" }}
        >
          Hard budget limits for LLM APIs
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-6">
          Stop unexpected
          <br />
          <span style={{ color: "var(--amber)" }}>LLM API bills</span>
        </h1>
        <p className="text-lg mb-10 max-w-xl mx-auto" style={{ color: "var(--muted)" }}>
          BudgetForge sits between your code and the LLM APIs. Set hard limits per project,
          get alerts before you blow your budget, and auto-downgrade to cheaper models when
          limits are reached.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/demo"
            className="px-6 py-3 rounded-lg font-semibold transition-opacity hover:opacity-90"
            style={{ background: "var(--amber)", color: "#000" }}
          >
            Try Demo
          </Link>
          <a
            href="https://github.com/majorelalexis-stack/budgetforge"
            className="px-6 py-3 rounded-lg transition-colors"
            style={{ border: "1px solid var(--border)" }}
          >
            View on GitHub
          </a>
        </div>
      </section>

      {/* Integration snippet */}
      <section className="max-w-2xl mx-auto px-6 pb-16">
        <div
          className="rounded-xl p-6 text-sm"
          style={{
            border: "1px solid var(--border)",
            background: "var(--card)",
            fontFamily: "var(--font-jetbrains-mono)",
          }}
        >
          <p className="text-xs mb-3" style={{ color: "var(--muted)" }}>
            2-line integration — works with any OpenAI SDK
          </p>
          <pre style={{ color: "#4ade80" }}>{`# Before
client = OpenAI(api_key="sk-...")

# After (drop-in replacement)
client = OpenAI(
  api_key="bf-yourprojectkey",
  base_url="https://llmbudget.maxiaworld.app/proxy/openai"
)`}</pre>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-4xl mx-auto px-6 pb-20">
        <h2 className="text-center text-2xl font-bold mb-10">Everything you need</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { icon: "🛑", title: "Hard Limits", desc: "Block or downgrade when budget is reached. No surprises." },
            { icon: "📊", title: "Per-Project Budgets", desc: "Separate budget, alerts and model policy per project." },
            { icon: "⬇️", title: "Auto-Downgrade", desc: "Automatically switch to cheaper models at threshold." },
            { icon: "🔔", title: "Alerts", desc: "Email and Slack/webhook alerts before you hit the ceiling." },
            { icon: "📥", title: "Usage Export", desc: "CSV and JSON export for billing, audits, and reporting." },
            { icon: "👥", title: "Team Members", desc: "Invite teammates as admin or viewer. No shared passwords." },
          ].map((f) => (
            <div
              key={f.title}
              className="rounded-xl p-5"
              style={{ border: "1px solid var(--border)", background: "var(--card)" }}
            >
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3 className="font-semibold mb-1">{f.title}</h3>
              <p className="text-sm" style={{ color: "var(--muted)" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section
        className="py-16 text-center px-6"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <h2 className="text-2xl font-bold mb-4">Ready to stop overspending?</h2>
        <Link
          href="/demo"
          className="inline-block px-8 py-3 rounded-lg font-semibold transition-opacity hover:opacity-90"
          style={{ background: "var(--amber)", color: "#000" }}
        >
          Try Demo →
        </Link>
      </section>
    </div>
  );
}
