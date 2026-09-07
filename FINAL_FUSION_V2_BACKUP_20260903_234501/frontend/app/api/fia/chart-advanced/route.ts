import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;
const BACKEND = process.env.FIA_BACKEND_URL || ("http:" + "//127.0.0.1:8001");

export async function POST(request: NextRequest) {
  try {
    const form = await request.formData();
    const response = await fetch(`${BACKEND}/api/chart/advanced-analyze`, {
      method: "POST",
      cache: "no-store",
      body: form,
    });
    const payload = await response.json();
    return NextResponse.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store, no-cache, must-revalidate" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, error: "Advanced chart proxy failed", detail: error?.message || String(error) },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
