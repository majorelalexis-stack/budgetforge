import { createHmac } from "crypto";

function computeSessionToken(secret: string): string {
  return createHmac("sha256", secret).update("session").digest("hex");
}

export async function POST(req: Request): Promise<Response> {
  const dashboardPassword = process.env.DASHBOARD_PASSWORD ?? "";
  const sessionSecret = process.env.SESSION_SECRET ?? "default-secret";

  // Dev mode: no password configured → always succeed
  if (!dashboardPassword) {
    const token = computeSessionToken(sessionSecret);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Set-Cookie": `bf_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`,
      },
    });
  }

  let body: { password?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { password } = body;
  if (password !== dashboardPassword) {
    return new Response(JSON.stringify({ error: "Invalid password" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const token = computeSessionToken(sessionSecret);
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": `bf_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`,
    },
  });
}

export async function DELETE(_req: Request): Promise<Response> {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": `bf_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`,
    },
  });
}
