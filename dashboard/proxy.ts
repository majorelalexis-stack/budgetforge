import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { createHmac } from "crypto";

const PROTECTED_PATHS = ["/dashboard", "/projects", "/activity", "/settings"];

function computeExpectedToken(secret: string): string {
  return createHmac("sha256", secret).update("session").digest("hex");
}

function isProtected(pathname: string): boolean {
  return PROTECTED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
}

export function proxy(request: NextRequest): NextResponse {
  const dashboardPassword = process.env.DASHBOARD_PASSWORD ?? "";

  // Dev mode: no password set → pass through
  if (!dashboardPassword) {
    return NextResponse.next();
  }

  const pathname = request.nextUrl.pathname;

  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  const sessionSecret = process.env.SESSION_SECRET ?? "default-secret";
  const expectedToken = computeExpectedToken(sessionSecret);
  const sessionCookie = request.cookies.get("bf_session")?.value;

  if (sessionCookie === expectedToken) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("from", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/dashboard/:path*", "/projects/:path*", "/activity/:path*", "/settings/:path*"],
};
