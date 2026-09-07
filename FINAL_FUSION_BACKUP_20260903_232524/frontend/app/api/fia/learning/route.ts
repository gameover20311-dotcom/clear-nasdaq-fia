import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND = process.env.FIA_BACKEND_URL || ("http:" + "//127.0.0.1:8001");

export async function GET() {
  try {
    const response = await fetch(`${BACKEND}/api/learning/status`, {
      cache: "no-store",
      headers: { "cache-control": "no-cache" },
    });
    const payload = await response.json();
    return NextResponse.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store, no-cache, must-revalidate" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, error: "FIA learning proxy failed", detail: error?.message || String(error) },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export async function POST() {
  try {
    const response = await fetch(`${BACKEND}/api/learning/resolve`, {
      method: "POST",
      cache: "no-store",
      headers: { "cache-control": "no-cache" },
    });
    const payload = await response.json();
    return NextResponse.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store, no-cache, must-revalidate" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, error: "FIA learning resolver proxy failed", detail: error?.message || String(error) },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
