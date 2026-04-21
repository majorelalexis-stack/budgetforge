import { POST, DELETE } from "../route";

describe("POST /api/auth", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv, DASHBOARD_PASSWORD: "testpassword", SESSION_SECRET: "testsecret" };
  });
  afterEach(() => { process.env = originalEnv; });

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
      body: JSON.stringify({ password: "wrong" }),
      headers: { "Content-Type": "application/json" },
    });
    const res = await POST(req);
    expect(res.status).toBe(401);
  });

  it("returns 200 when DASHBOARD_PASSWORD not set (dev mode)", async () => {
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

describe("DELETE /api/auth", () => {
  it("clears bf_session cookie", async () => {
    const req = new Request("http://localhost/api/auth", {
      method: "DELETE",
    });
    const res = await DELETE(req);
    expect(res.status).toBe(200);
    const setCookie = res.headers.get("Set-Cookie");
    expect(setCookie).toContain("bf_session=");
    expect(setCookie).toMatch(/Max-Age=0|expires=Thu, 01 Jan 1970/i);
  });
});
