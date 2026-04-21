"use client";

import { Suspense, useState, FormEvent } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Image from "next/image";

function LoginForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const from = searchParams.get("from") ?? "/dashboard";

  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        router.push(from);
      } else {
        setError("Invalid password");
      }
    } catch {
      setError("Connection error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="password" className="text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-lg px-3 py-2 text-sm focus:outline-none"
          style={{
            background: "var(--muted)",
            border: "1px solid var(--border)",
            color: "var(--foreground)",
          }}
          placeholder="••••••••"
          disabled={loading}
        />
      </div>

      {error && (
        <p
          className="text-sm text-center"
          style={{ color: "var(--red)" }}
          role="alert"
        >
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading}
        className="btn-amber w-full justify-center"
      >
        {loading ? "Signing in…" : "Sign in →"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--background)", color: "var(--foreground)" }}
    >
      <div
        className="w-full max-w-sm rounded-xl p-8"
        style={{ border: "1px solid var(--border)", background: "var(--card)" }}
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <Image
            src="/logo.png"
            alt="BudgetForge"
            width={48}
            height={48}
            className="rounded-xl mb-3"
          />
          <span className="font-bold text-lg tracking-tight">
            LLM <span style={{ color: "var(--amber)" }}>BudgetForge</span>
          </span>
          <p className="text-sm mt-1" style={{ color: "var(--muted-fg)" }}>
            Enter your dashboard password
          </p>
        </div>

        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
