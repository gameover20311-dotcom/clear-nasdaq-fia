import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND = process.env.FIA_BACKEND_URL || ("http:" + "//127.0.0.1:8001");

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND}/api/confluence`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json", "cache-control": "no-cache" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    return NextResponse.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store, no-cache, must-revalidate" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, error: "FIA confluence proxy failed", detail: error?.message || String(error) },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
