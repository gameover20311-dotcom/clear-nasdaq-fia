import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND = process.env.FIA_BACKEND_URL || "http://127.0.0.1:8001";

/* Proxy for the full Chart Analyst report.
 *
 * Streams the uploaded image and the user's own analysis to the backend, which
 * runs the INDEPENDENT vision pass first and only then compares it against
 * verified FIA evidence. This route adds no interpretation of its own.
 */
export async function POST(request: Request) {
  const controller = new AbortController();
  // Vision + snapshot + cognitive can legitimately take a while.
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const inbound = await request.formData();
    const outbound = new FormData();
    for (const [key, value] of inbound.entries()) outbound.append(key, value as any);

    const response = await fetch(`${BACKEND}/api/chart/analyst-report`, {
      method: "POST",
      body: outbound,
      cache: "no-store",
      signal: controller.signal,
    });

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      return NextResponse.json(
        {
          ok: false,
          status: "UNAVAILABLE",
          error: "Chart analyst unavailable",
          detail: payload?.detail || `Backend HTTP ${response.status}`,
        },
        { status: response.status, headers: { "Cache-Control": "no-store" } }
      );
    }
    return NextResponse.json(payload, {
      status: 200,
      headers: { "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0" },
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Unknown backend error";
    return NextResponse.json(
      { ok: false, status: "UNAVAILABLE", error: "Chart analyst unavailable", detail: message },
      { status: 502, headers: { "Cache-Control": "no-store" } }
    );
  } finally {
    clearTimeout(timeout);
  }
}
