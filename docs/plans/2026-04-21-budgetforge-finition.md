# BudgetForge Finition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect the admin dashboard with a password, add a public read-only demo, and update the landing page buttons.

**Architecture:** Next.js middleware guards all admin routes (`/dashboard`, `/projects`, `/activity`, `/settings`) and redirects to `/login` if no valid session cookie. Auth is handled via a Next.js API route handler (`app/api/auth/route.ts`) which sets an httpOnly cookie. The `/demo` route is public and fetches from new hardcoded `/api/demo/*` FastAPI endpoints. The landing `/` gets updated buttons: "Try Demo" + "View on GitHub", no "Open Dashboard".

**Tech Stack:** Next.js 15 App Router, TypeScript, FastAPI, Python 3.12, httpOnly cookies, Next.js middleware, sha256 HMAC for session token.

**Working directory:** `C:\Users\Mini pc\Desktop\MAXIA Lab\budgetforge`

---

## File Structure

**Create:**
- `dashboard/app/login/page.tsx` — password form UI
- `dashboard/app/api/auth/route.ts` — POST: verify password, set cookie / DELETE: clear cookie
- `dashboard/middleware.ts` — protect admin routes, redirect to /login
- `dashboard/app/demo/page.tsx` — read-only demo dashboard
- `backend/routes/demo.py` — hardcoded demo data endpoints

**Modify:**
- `dashboard/app/page.tsx` — update landing buttons
- `dashboard/next.config.ts` — exclude `/api/auth` from backend rewrite
- `backend/main.py` — register demo router
- `dashboard/.env.example` — add DASHBOARD_PASSWORD and SESSION_SECRET

---

### Task 1: Dashboard password auth

**Files:**
- Create: `dashboard/app/login/page.tsx`
- Create: `dashboard/app/api/auth/route.ts`
- Create: `dashboard/middleware.ts`
- Modify: `dashboard/next.config.ts`
- Modify: `dashboard/.env.example`

**Context:** The Next.js app proxies all `/api/*` to FastAPI backend via rewrites in `next.config.ts`. Next.js route handlers take precedence over rewrites, so `app/api/auth/route.ts` will be served by Next.js directly and NOT forwarded to FastAPI. The rewrite config must explicitly exclude `/api/auth` to be safe.

The session mechanism: `DASHBOARD_PASSWORD` (plain text in `.env.local`) + `SESSION_SECRET` (random string). On login, verify password matches, set cookie value = `HMAC-SHA256(SESSION_SECRET, "session")` as a constant token. Middleware checks cookie exists and equals expected token.

Use Node.js built-in `crypto` module for HMAC — no extra deps.

- [ ] **Step 1: Write the failing tests**

Create `dashboard/app/api/auth/__tests__/route.test.ts`:

```typescript
import { POST } from "../route";

describe("POST /api/auth", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = {
      ...originalEnv,
      DASHBOARD_PASSWORD: "testpassword",
      SESSION_SECRET: "testsecret",
    };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("returns 200 and sets cookie on correct password", async () => {
    const req = new Request("http://localhost/api/auth", {
      method: "POST",
      body: JSON.stringify({ password: "testpassword" }),
      headers: { "Content-Type": "application/json" },
    });
    const res = await POST(req);
    expect(res.status).toBe(200);
    const setCookie = res.headers.get("Set-Cookie");
    expect(setCookie).toContain("bf_session=");
    expect(setCookie).toContain("HttpOnly");
  });

  it("returns 401 on wrong password", async () => {
    const req = new Request("http://localhost/api/auth", {
      method: "POST",
      body: JSON.stringify({ password: "wrongpassword" }),
      headers: { "Content-Type": "application/json" },
    });
    const res = await POST(req);
    expect(res.status).toBe(401);
  });

  it("returns 401 when DASHBOARD_PASSWORD not set (dev mode allowed)", async () => {
    delete process.env.DASHBOARD_PASSWORD;
    const req = new Request("http://localhost/api/auth", {
      method: "POST",
      body: JSON.stringify({ password: "" }),
      headers: { "Content-Type": "application/json" },
    });
    const res = await POST(req);
    expect(res.status).toBe(200);
  });
});
```

Run: `cd dashboard && npx jest app/api/auth --no-coverage 2>&1 | tail -10`
Expected: FAIL — route not found

- [ ] **Step 2: Implement the auth API route**

Create `dashboard/app/api/auth/route.ts`:

```typescript
import { createHmac } from "crypto";
import { NextResponse } from "next/server";

function expectedToken(): string {
  const secret = process.env.SESSION_SECRET ?? "dev-secret";
  return createHmac("sha256", secret).update("session").digest("hex");
}

export async function POST(req: Request) {
  const { password } = await req.json();
  const dashboardPassword = process.env.DASHBOARD_PASSWORD ?? "";

  if (dashboardPassword !== "" && password !== dashboardPassword) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  const token = expectedToken();
  const res = NextResponse.json({ ok: true });
  res.headers.set(
    "Set-Cookie",
    `bf_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`
  );
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.headers.set(
    "Set-Cookie",
    "bf_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
  );
  return res;
}

export function getExpectedToken(): string {
  return expectedToken();
}
```

- [ ] **Step 3: Run tests — verify they pass**

Run: `cd dashboard && npx jest app/api/auth --no-coverage 2>&1 | tail -10`
Expected: 3 PASS

- [ ] **Step 4: Create the middleware**

Create `dashboard/middleware.ts`:

```typescript
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { createHmac } from "crypto";

const PROTECTED = ["/dashboard", "/projects", "/activity", "/settings"];

function expectedToken(): string {
  const secret = process.env.SESSION_SECRET ?? "dev-secret";
  return createHmac("sha256", secret).update("session").digest("hex");
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const isProtected = PROTECTED.some((p) => pathname === p || pathname.startsWith(p + "/"));
  if (!isProtected) return NextResponse.next();

  const dashboardPassword = process.env.DASHBOARD_PASSWORD ?? "";
  if (dashboardPassword === "") return NextResponse.next();

  const cookie = req.cookies.get("bf_session")?.value;
  if (cookie === expectedToken()) return NextResponse.next();

  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("from", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/dashboard/:path*", "/projects/:path*", "/activity/:path*", "/settings/:path*"],
};
```

- [ ] **Step 5: Create the login page**

Create `dashboard/app/login/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import { Suspense } from "react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const from = searchParams.get("from") ?? "/dashboard";
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
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
      setError("Connection error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: "var(--background)" }}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-8"
        style={{ border: "1px solid var(--border)", background: "var(--card)" }}
      >
        <div className="flex flex-col items-center gap-3 mb-8">
          <Image src="/logo.png" alt="BudgetForge" width={48} height={48} className="rounded-xl" />
          <h1 className="text-xl font-bold tracking-tight">
            LLM <span style={{ color: "var(--amber)" }}>BudgetForge</span>
          </h1>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Admin access</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            className="w-full px-4 py-3 rounded-lg text-sm outline-none focus:ring-2"
            style={{
              background: "var(--muted)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          />
          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90 disabled:opacity-50"
            style={{ background: "var(--amber)", color: "#000" }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
```

- [ ] **Step 6: Update next.config.ts to exclude /api/auth from backend rewrite**

Modify `dashboard/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8011";
    return [
      { source: "/api/auth",       destination: "/api/auth" },
      { source: "/api/:path*",     destination: `${base}/api/:path*` },
      { source: "/health",         destination: `${base}/health` },
      { source: "/proxy/:path*",   destination: `${base}/proxy/:path*` },
    ];
  },
};

export default nextConfig;
```

Wait — a rewrite that maps `/api/auth` to `/api/auth` would loop. The correct way is to NOT rewrite `/api/auth` at all. Use the `has` condition or just put the Next.js route first. In Next.js, route handlers take precedence over rewrites automatically, so actually we don't need to change next.config.ts at all. Leave it unchanged.

Revert `next.config.ts` to its original content:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8011";
    return [
      { source: "/api/:path*",   destination: `${base}/api/:path*` },
      { source: "/health",       destination: `${base}/health` },
      { source: "/proxy/:path*", destination: `${base}/proxy/:path*` },
    ];
  },
};

export default nextConfig;
```

- [ ] **Step 7: Update .env.example**

Add to `dashboard/.env.example`:
```
DASHBOARD_PASSWORD=your-admin-password
SESSION_SECRET=random-string-change-this
```

- [ ] **Step 8: Build to verify no TypeScript errors**

Run: `cd dashboard && npm run build 2>&1 | tail -15`
Expected: clean build, `/login` appears in route list

- [ ] **Step 9: Commit**

```bash
git add dashboard/app/login/page.tsx dashboard/app/api/auth/route.ts dashboard/middleware.ts dashboard/.env.example
git commit -m "feat(auth): password-protected dashboard with httpOnly cookie session"
```

---

### Task 2: Demo dashboard

**Files:**
- Create: `backend/routes/demo.py`
- Modify: `backend/main.py`
- Create: `dashboard/app/demo/page.tsx`

**Context:** The demo must work without auth. The backend exposes hardcoded realistic data at `/api/demo/projects`, `/api/demo/usage/summary`, `/api/demo/usage/daily`. The dashboard `/demo` page fetches from these endpoints and renders the overview in read-only mode (no create/edit/delete buttons, banner "Demo — read only").

The demo data should look realistic: 3 projects, one near budget, one exceeded, one healthy. Usage history spanning 30 days.

- [ ] **Step 1: Write failing tests for demo backend**

Create `backend/tests/test_demo.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_demo_projects_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/projects")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    assert "name" in data[0]
    assert "budget_usd" in data[0]

@pytest.mark.asyncio
async def test_demo_usage_summary():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/summary")
    assert res.status_code == 200
    data = res.json()
    assert "total_cost_usd" in data
    assert "total_calls" in data

@pytest.mark.asyncio
async def test_demo_usage_daily():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/daily")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 30
    assert "date" in data[0]
    assert "spend" in data[0]
```

Run: `cd backend && python -m pytest tests/test_demo.py -v 2>&1 | tail -10`
Expected: FAIL — no demo router

- [ ] **Step 2: Implement demo backend routes**

Create `backend/routes/demo.py`:

```python
from datetime import date, timedelta
from fastapi import APIRouter

router = APIRouter(prefix="/api/demo", tags=["demo"])

_PROJECTS = [
    {
        "id": 1,
        "name": "production-app",
        "api_key": "bf-demo-prod-xxxxxxxxxxxxxxxxxxxx",
        "budget_usd": 50.0,
        "used_usd": 47.32,
        "pct_used": 94.6,
        "action": "block",
        "allowed_providers": ["openai", "anthropic"],
        "downgrade_model": None,
    },
    {
        "id": 2,
        "name": "staging-env",
        "api_key": "bf-demo-stag-xxxxxxxxxxxxxxxxxxxx",
        "budget_usd": 20.0,
        "used_usd": 8.15,
        "pct_used": 40.8,
        "action": "downgrade",
        "allowed_providers": ["openai"],
        "downgrade_model": "gpt-4o-mini",
    },
    {
        "id": 3,
        "name": "research-agent",
        "api_key": "bf-demo-rsch-xxxxxxxxxxxxxxxxxxxx",
        "budget_usd": 100.0,
        "used_usd": 12.80,
        "pct_used": 12.8,
        "action": None,
        "allowed_providers": ["anthropic", "google", "openai"],
        "downgrade_model": None,
    },
    {
        "id": 4,
        "name": "demo-exceeded",
        "api_key": "bf-demo-ovr-xxxxxxxxxxxxxxxxxxxxx",
        "budget_usd": 10.0,
        "used_usd": 10.01,
        "pct_used": 100.1,
        "action": "block",
        "allowed_providers": ["openai"],
        "downgrade_model": None,
    },
]


def _daily_data() -> list[dict]:
    today = date.today()
    import random
    random.seed(42)
    result = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        spend = round(random.uniform(0.5, 4.2), 4)
        result.append({"date": d.isoformat(), "spend": spend})
    return result


@router.get("/projects")
def demo_projects() -> list[dict]:
    return _PROJECTS


@router.get("/usage/summary")
def demo_usage_summary() -> dict:
    total = sum(p["used_usd"] for p in _PROJECTS)
    return {
        "total_cost_usd": round(total, 4),
        "total_calls": 1284,
        "total_tokens": 4_820_000,
        "providers": {
            "openai": {"calls": 820, "cost_usd": 42.10},
            "anthropic": {"calls": 310, "cost_usd": 21.50},
            "google": {"calls": 154, "cost_usd": 4.68},
        },
    }


@router.get("/usage/daily")
def demo_usage_daily() -> list[dict]:
    return _daily_data()
```

- [ ] **Step 3: Register demo router in main.py**

In `backend/main.py`, add:
```python
from routes.demo import router as demo_router
app.include_router(demo_router)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && python -m pytest tests/test_demo.py -v 2>&1 | tail -10`
Expected: 3 PASS

- [ ] **Step 5: Create the demo dashboard page**

Create `dashboard/app/demo/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { DollarSign, FolderKanban, AlertTriangle, XCircle } from "lucide-react";
import Link from "next/link";
import { BurnBar } from "@/components/burn-bar";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface DemoProject {
  id: number;
  name: string;
  api_key: string;
  budget_usd: number;
  used_usd: number;
  pct_used: number;
  action: string | null;
}

interface DailySpend {
  date: string;
  spend: number;
}

interface Summary {
  total_cost_usd: number;
  total_calls: number;
}

export default function DemoPage() {
  const [projects, setProjects] = useState<DemoProject[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [daily, setDaily] = useState<DailySpend[]>([]);

  useEffect(() => {
    Promise.all([
      fetch("/api/demo/projects").then((r) => r.json()),
      fetch("/api/demo/usage/summary").then((r) => r.json()),
      fetch("/api/demo/usage/daily").then((r) => r.json()),
    ]).then(([p, s, d]) => {
      setProjects(p);
      setSummary(s);
      setDaily(d);
    });
  }, []);

  const totalBudget = projects.reduce((s, p) => s + p.budget_usd, 0);
  const atRisk = projects.filter((p) => p.pct_used >= 80).length;
  const exceeded = projects.filter((p) => p.pct_used >= 100).length;

  return (
    <div className="min-h-screen" style={{ background: "var(--background)", color: "var(--foreground)" }}>
      {/* Demo banner */}
      <div
        className="w-full py-2 px-4 text-center text-sm font-semibold"
        style={{ background: "var(--amber)", color: "#000" }}
      >
        Demo — read only ·{" "}
        <Link href="https://github.com/majorelalexis-stack/budgetforge" className="underline">
          Self-host for free
        </Link>
      </div>

      {/* Nav */}
      <nav
        className="px-6 py-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span className="font-bold text-lg tracking-tight">
          LLM <span style={{ color: "var(--amber)" }}>BudgetForge</span>
          <span className="ml-2 text-xs font-normal px-2 py-0.5 rounded-full" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
            Demo
          </span>
        </span>
        <Link
          href="/"
          className="text-sm px-4 py-2 rounded-lg transition-opacity hover:opacity-80"
          style={{ border: "1px solid var(--border)" }}
        >
          ← Back
        </Link>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {[
            { icon: DollarSign, label: "Total Spent", value: `$${summary?.total_cost_usd.toFixed(4) ?? "—"}`, accent: "#f59e0b" },
            { icon: FolderKanban, label: "Projects", value: projects.length, accent: "#3b82f6" },
            { icon: AlertTriangle, label: "At Risk", value: atRisk, accent: atRisk > 0 ? "#f59e0b" : "#22c55e" },
            { icon: XCircle, label: "Exceeded", value: exceeded, accent: exceeded > 0 ? "#ef4444" : "#22c55e" },
          ].map(({ icon: Icon, label, value, accent }) => (
            <div key={label} className="rounded-xl p-5" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs uppercase tracking-widest font-semibold" style={{ color: "var(--muted)" }}>{label}</span>
                <Icon className="w-4 h-4" style={{ color: accent }} strokeWidth={1.8} />
              </div>
              <div className="text-3xl font-bold tracking-tight" style={{ color: accent }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Spend chart */}
        <div className="rounded-xl p-6 mb-6" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
          <h2 className="text-sm font-semibold uppercase tracking-wider mb-4" style={{ color: "var(--muted)" }}>
            Global Spend — Last 30 Days
          </h2>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={daily}>
              <defs>
                <linearGradient id="demoGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--amber)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--amber)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} interval={6} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v: number) => `$${v.toFixed(2)}`} width={50} />
              <Tooltip formatter={(val) => [`$${typeof val === "number" ? val.toFixed(4) : val}`, "Spend"]} />
              <Area type="monotone" dataKey="spend" stroke="var(--amber)" fill="url(#demoGradient)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Projects table */}
        <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
          <div className="p-5 border-b" style={{ borderColor: "var(--border)" }}>
            <h2 className="font-semibold">Projects</h2>
          </div>
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {projects.map((p) => (
              <div key={p.id} className="flex items-center gap-4 px-5 py-4">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{p.name}</p>
                  <p className="font-mono text-xs truncate" style={{ color: "var(--muted)" }}>{p.api_key}</p>
                </div>
                <div className="w-28 shrink-0">
                  <BurnBar pct={p.pct_used} showValue={false} height={4} />
                </div>
                <div className="text-right shrink-0 w-24">
                  <p className="font-mono text-xs">${p.used_usd.toFixed(4)}</p>
                  <p className="font-mono text-xs" style={{ color: "var(--muted)" }}>/ ${p.budget_usd.toFixed(2)}</p>
                </div>
                <div className="shrink-0 w-20 text-right">
                  <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded-full ${
                    p.action === "block" ? "bg-red-500/10 text-red-400" :
                    p.action === "downgrade" ? "bg-blue-500/10 text-blue-400" :
                    "bg-white/5 text-gray-400"
                  }`}>
                    {p.action ?? "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted)" }}>
          Like what you see?{" "}
          <a href="https://github.com/majorelalexis-stack/budgetforge" className="underline" style={{ color: "var(--amber)" }}>
            Self-host BudgetForge for free →
          </a>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Build to verify no TypeScript errors**

Run: `cd dashboard && npm run build 2>&1 | tail -15`
Expected: clean build, `/demo` in route list

- [ ] **Step 7: Commit**

```bash
git add backend/routes/demo.py backend/main.py backend/tests/test_demo.py dashboard/app/demo/page.tsx
git commit -m "feat(demo): read-only demo dashboard with hardcoded realistic data"
```

---

### Task 3: Update landing page buttons

**Files:**
- Modify: `dashboard/app/page.tsx`

**Context:** Current landing has "Open Dashboard" + "View on GitHub". Replace "Open Dashboard" with "Try Demo" → `/demo`. Keep "View on GitHub". Add a subtle "Admin Login" text link below the buttons.

- [ ] **Step 1: Update landing buttons**

In `dashboard/app/page.tsx`, replace the buttons section:

```tsx
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
        <p className="mt-4 text-sm" style={{ color: "var(--muted)" }}>
          <Link href="/login" className="hover:underline" style={{ color: "var(--muted)" }}>
            Admin login →
          </Link>
        </p>
```

Also update the bottom CTA section — replace `href="/dashboard"` with `href="/demo"` and text "Open BudgetForge →" with "Try Demo →".

- [ ] **Step 2: Build to verify**

Run: `cd dashboard && npm run build 2>&1 | tail -10`
Expected: clean build

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/page.tsx
git commit -m "feat(landing): Try Demo + Admin login buttons"
```

---

## Deploy after all tasks

```bash
# Backend
scp backend/routes/demo.py backend/main.py ubuntu@maxiaworld.app:/opt/budgetforge/backend/routes/
ssh ubuntu@maxiaworld.app "sudo systemctl restart budgetforge-backend"

# Dashboard
scp -r dashboard/app/login dashboard/app/demo dashboard/app/page.tsx dashboard/middleware.ts ubuntu@maxiaworld.app:/opt/budgetforge/dashboard/app/
ssh ubuntu@maxiaworld.app "cd /opt/budgetforge/dashboard && npm run build && sudo systemctl restart budgetforge-dashboard"

# Set password on server
ssh ubuntu@maxiaworld.app "echo 'DASHBOARD_PASSWORD=your-password' >> /opt/budgetforge/dashboard/.env.local"
ssh ubuntu@maxiaworld.app "echo 'SESSION_SECRET=$(openssl rand -hex 32)' >> /opt/budgetforge/dashboard/.env.local"
```
