import { NextRequest, NextResponse } from "next/server";
import { BACKEND, clearSessionCookie, parseBackendResponse, SESSION_COOKIE } from "../../../../lib/auth-server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ ok: false, detail: "MISSING_SESSION" }, { status: 401 });
  try {
    const upstream = await fetch(`${BACKEND}/api/auth/session`, {
      cache: "no-store",
      headers: { authorization: `Bearer ${token}`, "cache-control": "no-cache" },
    });
    const { body, ok } = await parseBackendResponse(upstream);
    if (!ok || body?.ok !== true) {
      const result = NextResponse.json({ ok: false, detail: body?.detail || "INVALID_SESSION" }, { status: 401 });
      clearSessionCookie(result);
      return result;
    }
    return NextResponse.json(body, { status: 200, headers: { "Cache-Control": "no-store" } });
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : "AUTH_BACKEND_UNAVAILABLE";
    return NextResponse.json({ ok: false, detail }, { status: 503 });
  }
}
