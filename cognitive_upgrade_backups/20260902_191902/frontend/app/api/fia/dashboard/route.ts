import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND =
  process.env.FIA_BACKEND_URL || ("http:" + "//127.0.0.1:8001");

async function getJson(path: string) {
  const r = await fetch(`${BACKEND}${path}`, {
    cache: "no-store",
    headers: {
      "cache-control": "no-cache",
    },
  });

  if (!r.ok) {
    throw new Error(`${path} HTTP ${r.status}`);
  }

  return await r.json();
}

function forecastValid(v: any) {
  return Boolean(
    v &&
    typeof v === "object" &&
    v.direction &&
    v.bullish_probability !== undefined &&
    v.bearish_probability !== undefined
  );
}

function snapshotValid(v: any) {
  const d = v?.data && typeof v.data === "object" ? v.data : v;
  return Boolean(d && typeof d === "object" && d.price !== undefined);
}

export async function GET() {
  try {
    let dashboard: any = {};

    try {
      dashboard = await getJson(`/api/dashboard?t=${Date.now()}`);
    } catch {}

    let snapshot = dashboard?.live?.snapshot;
    let forecast = dashboard?.live?.forecast;
    let liquidity = dashboard?.live?.liquidity;

    if (!snapshotValid(snapshot)) {
      snapshot = await getJson(`/api/snapshot?t=${Date.now()}`);
    }

    if (!forecastValid(forecast)) {
      forecast = await getJson(`/api/forecast?t=${Date.now()}`);
    }

    if (!liquidity || typeof liquidity !== "object") {
      const rawLiquidity = await getJson(`/api/liquidity?t=${Date.now()}`);
      liquidity = rawLiquidity?.levels || rawLiquidity;
    }

    const payload = {
      ok: true,
      generated_at:
        dashboard?.generated_at || new Date().toISOString(),

      live: {
        snapshot,
        forecast,
        liquidity,
        upcoming_earnings:
          dashboard?.live?.upcoming_earnings || {
            available: false,
            events: [],
          },
      },

      backtest: dashboard?.backtest || {},
    };

    return NextResponse.json(payload, {
      status: 200,
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Surrogate-Control": "no-store",
        Pragma: "no-cache",
        Expires: "0",
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      {
        ok: false,
        error: "FIA live proxy failed",
        detail: error?.message || String(error),
      },
      {
        status: 502,
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  }
}
