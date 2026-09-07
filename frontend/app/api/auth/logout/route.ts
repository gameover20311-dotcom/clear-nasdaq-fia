import { NextRequest, NextResponse } from "next/server";
import { BACKEND, clearSessionCookie, SESSION_COOKIE } from "../../../../lib/auth-server";

export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) {
    await fetch(`${BACKEND}/api/auth/logout`, {
      method: "POST",
      cache: "no-store",
      headers: { authorization: `Bearer ${token}`, "cache-control": "no-cache" },
    }).catch(() => null);
  }
  const response = NextResponse.json({ ok: true }, { status: 200, headers: { "Cache-Control": "no-store" } });
  clearSessionCookie(response);
  return response;
}
