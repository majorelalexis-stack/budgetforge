"use client";
import { useState, FormEvent } from "react";
import Link from "next/link";

export function FreeSignupForm() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/signup/free", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (resp.status === 429) {
        setError("Too many attempts from this connection. Try again tomorrow.");
        return;
      }
      if (!resp.ok) throw new Error();
      setDone(true);
    } catch {
      setError("Something went wrong — please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="text-center">
        <p className="text-xl font-semibold mb-2">Check your inbox!</p>
        <p className="text-sm mb-4" style={{ color: "#c8d8e8" }}>
          Your BudgetForge key was sent to <strong>{email}</strong>.
        </p>
        <Link href="/portal" className="text-sm hover:opacity-80" style={{ color: "var(--amber)" }}>
          Already have it? Access your keys →
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 items-center w-full">
      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 justify-center w-full max-w-md">
        <input
          type="email"
          required
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="flex-1 px-4 py-3 rounded-lg text-sm outline-none"
          style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--foreground)" }}
        />
        <button
          type="submit"
          disabled={loading}
          className="px-6 py-3 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90 disabled:opacity-50 whitespace-nowrap"
          style={{ background: "var(--amber)", color: "#000" }}
        >
          {loading ? "Sending…" : "Get my free key →"}
        </button>
      </form>
      {error && <p className="text-xs" style={{ color: "#ef4444" }}>{error}</p>}
      <p className="text-xs" style={{ color: "#c8d8e8" }}>
        Already have a key?{" "}
        <Link href="/portal" style={{ color: "var(--amber)" }} className="hover:opacity-80">
          Access your portal →
        </Link>
      </p>
    </div>
  );
}
