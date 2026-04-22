/**
 * P1.4 TDD RED — proxy.ts : tokens timestamp-based (ts.hmac)
 * Vérifie que :
 * - token valide (hmac ok, < 24h) → pass through
 * - token expiré (> 24h) → redirect /login
 * - HMAC invalide → redirect /login
 * - ancien format statique (sans timestamp) → redirect /login
 * - aucun cookie → redirect /login
 */
import { proxy } from "../proxy";
import { NextRequest } from "next/server";
import { createHmac } from "crypto";

const SECRET = "testsecret";
const PASSWORD = "testpassword";

function makeToken(ts: number, secret: string): string {
  const tsStr = ts.toString();
  const hmac = createHmac("sha256", secret).update(tsStr).digest("hex");
  return `${tsStr}.${hmac}`;
}

function makeRequest(pathname: string, token?: string): NextRequest {
  const headers: HeadersInit = token ? { Cookie: `bf_session=${token}` } : {};
  return new NextRequest(`https://localhost${pathname}`, { headers });
}

describe("proxy — timestamp token verification (P1.4)", () => {
  const origEnv = process.env;

  beforeEach(() => {
    process.env = { ...origEnv, SESSION_SECRET: SECRET, DASHBOARD_PASSWORD: PASSWORD };
  });
  afterEach(() => {
    process.env = origEnv;
  });

  it("valid token (correct HMAC, recent timestamp) → not a redirect", () => {
    const token = makeToken(Date.now(), SECRET);
    const req = makeRequest("/dashboard", token);
    const resp = proxy(req);
    expect(resp.headers.get("location")).toBeNull();
  });

  it("expired token (> 24h old) → redirect to /login", () => {
    const ts = Date.now() - 25 * 3600 * 1000;
    const token = makeToken(ts, SECRET);
    const req = makeRequest("/dashboard", token);
    const resp = proxy(req);
    expect(resp.headers.get("location")).toContain("/login");
  });

  it("wrong HMAC → redirect to /login", () => {
    const ts = Date.now();
    const token = `${ts}.badhashbadhashbadhashbadhashbadhashbadhashbadhashbadhashbadhash`;
    const req = makeRequest("/dashboard", token);
    const resp = proxy(req);
    expect(resp.headers.get("location")).toContain("/login");
  });

  it("old static token format (no timestamp) → redirect to /login", () => {
    const oldToken = createHmac("sha256", SECRET).update("session").digest("hex");
    const req = makeRequest("/dashboard", oldToken);
    const resp = proxy(req);
    expect(resp.headers.get("location")).toContain("/login");
  });

  it("no cookie → redirect to /login", () => {
    const req = makeRequest("/dashboard");
    const resp = proxy(req);
    expect(resp.headers.get("location")).toContain("/login");
  });

  it("dev mode (no DASHBOARD_PASSWORD) → pass through without cookie", () => {
    delete process.env.DASHBOARD_PASSWORD;
    const req = makeRequest("/dashboard");
    const resp = proxy(req);
    expect(resp.headers.get("location")).toBeNull();
  });

  it("non-protected path → pass through", () => {
    const req = makeRequest("/login");
    const resp = proxy(req);
    expect(resp.headers.get("location")).toBeNull();
  });
});
