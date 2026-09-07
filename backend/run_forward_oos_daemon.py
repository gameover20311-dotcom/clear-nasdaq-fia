#!/usr/bin/env python3
"""Autonomous zero-cost Forward OOS collector for macOS/terminal use.

Runs continuously. It resolves due outcomes and only creates a new forecast
inside the sealed 13:00 America/New_York checkpoint window. No backfill exists.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from fia.engine import build_forecast
from fia.forward_oos_api import run_once
from fia.providers import ProviderHub


async def main() -> None:
    hub = ProviderHub()
    interval = max(30, int(os.getenv("FIA_FORWARD_OOS_POLL_SECONDS", "60") or "60"))
    print("CLEAR NASDAQ SOL56 NEW FORWARD OOS DAEMON")
    print("checkpoint=13:00 America/New_York | backfill=BLOCKED | BASE_FIA=FROZEN")
    while True:
        try:
            result = await run_once(hub, build_forecast)
            lock = result.get("lock", {})
            resolution = result.get("resolution", {})
            report = result.get("report", {})
            print(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(),
                "lock_created": lock.get("created"),
                "lock_reason": lock.get("reason"),
                "resolved_now": resolution.get("resolved"),
                "forward_records": report.get("new_forward_forecasts_locked"),
                "stage": report.get("stage"),
                "promotion": (report.get("promotion") or {}).get("verdict"),
                "ledger_ok": (report.get("ledger_integrity") or {}).get("ok"),
            }, separators=(",", ":")), flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "error": repr(exc)}), flush=True)
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
