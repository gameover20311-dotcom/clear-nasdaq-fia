import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export const revalidate = 0;
const BACKEND = process.env.FIA_BACKEND_URL || "http://127.0.0.1:8001";
function isObject(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === "object" && !Array.isArray(value)); }
function finiteNumber(value: unknown): boolean {
  if (value === null || value === undefined || typeof value === "boolean") return false;
  if (typeof value === "string" && value.trim() === "") return false;
  return Number.isFinite(Number(value));
}
function isAtomicDashboard(value: unknown) {
  if (!isObject(value) || value.ok !== true || !isObject(value.live)) return false;
  const live = value.live as Record<string, unknown>;
  if (!isObject(live.snapshot) || !isObject(live.forecast)) return false;
  const forecast = live.forecast as Record<string, unknown>;
  return typeof forecast.direction === "string" && finiteNumber(forecast.bullish_probability) && finiteNumber(forecast.bearish_probability);
}
export async function GET() {
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(`${BACKEND}/api/final/dashboard`, { cache:"no-store", headers:{"cache-control":"no-cache"}, signal:controller.signal });
    if (!response.ok) throw new Error(`Backend HTTP ${response.status}`);
    const payload = await response.json(); if (!isAtomicDashboard(payload)) throw new Error("Invalid final atomic dashboard payload");
    return NextResponse.json(payload,{status:200,headers:{"Cache-Control":"no-store, no-cache, must-revalidate, max-age=0",Pragma:"no-cache",Expires:"0"}});
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Unknown backend error";
    return NextResponse.json({ok:false,status:"UNAVAILABLE",error:"FIA final atomic dashboard unavailable",detail:message},{status:502,headers:{"Cache-Control":"no-store"}});
  } finally { clearTimeout(timeout); }
}
