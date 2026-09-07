#!/usr/bin/env python3
"""Manual one-shot Forward OOS collector.

Safe to run repeatedly. It will resolve due records and create a forecast only
inside the configured live 13:00 ET checkpoint window. It never backfills.
"""
import asyncio
import json
from fia.providers import ProviderHub
from fia.engine import build_forecast
from fia.forward_oos_api import run_once

async def main():
    result = await run_once(ProviderHub(), build_forecast)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
