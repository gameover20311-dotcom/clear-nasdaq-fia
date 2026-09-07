import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.FIA_BACKEND_URL || "http://127.0.0.1:8001";
const COOKIE = "fia_session";

export async function proxy(request: NextRequest) {
  const token = request.cookies.get(COOKIE)?.value;
  const isApi = request.nextUrl.pathname.startsWith("/api/");

  if (!token) {
    if (isApi) return NextResponse.json({ ok: false, detail: "AUTH_REQUIRED" }, { status: 401 });
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }

  try {
    const check = await fetch(`${BACKEND}/api/auth/session`, {
      cache: "no-store",
      headers: { authorization: `Bearer ${token}`, "cache-control": "no-cache" },
    });
    if (check.ok) return NextResponse.next();
  } catch {
    if (isApi) return NextResponse.json({ ok: false, detail: "AUTH_SERVICE_UNAVAILABLE" }, { status: 503 });
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("reason", "auth-service-unavailable");
    return NextResponse.redirect(url);
  }

  if (isApi) return NextResponse.json({ ok: false, detail: "AUTH_REQUIRED" }, { status: 401 });
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  return NextResponse.redirect(url);
}

export const config = {
  // Everything except public auth pages/endpoints and Next static assets is FULL_ACCESS gated.
  matcher: ["/((?!api/auth|login|signup|_next/static|_next/image|favicon.ico).*)"],
};
