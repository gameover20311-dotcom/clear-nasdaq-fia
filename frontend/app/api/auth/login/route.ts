import { NextRequest, NextResponse } from "next/server";
import { BACKEND, parseBackendResponse, setSessionCookie } from "../../../../lib/auth-server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const upstream = await fetch(`${BACKEND}/api/auth/login`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json", "cache-control": "no-cache" },
      body: JSON.stringify(payload),
    });
    const { body, ok } = await parseBackendResponse(upstream);
    if (!ok || body?.ok !== true || typeof body?.token !== "string") {
      return NextResponse.json({ ok: false, detail: body?.detail || "LOGIN_FAILED" }, { status: upstream.status || 401 });
    }
    const result = NextResponse.json({ ok: true, user: body.user }, { status: 200, headers: { "Cache-Control": "no-store" } });
    setSessionCookie(result, body.token, Number(body.expires_in) || undefined);
    return result;
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : "AUTH_BACKEND_UNAVAILABLE";
    return NextResponse.json({ ok: false, detail }, { status: 503 });
  }
}
