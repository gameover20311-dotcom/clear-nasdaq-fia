from pathlib import Path
import sys, tempfile, time, asyncio

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import fia.forexcom_chart_liquidity as m

def check(name, cond, detail=None):
    if not cond:
        raise AssertionError(f"{name} FAIL {detail}")
    print("PASS", name)

async def main():
    with tempfile.TemporaryDirectory() as d:
        old_store = m.STORE
        m.STORE = Path(d) / "latest.json"
        try:
            payload = {
                "symbol": "FOREXCOM:NAS100",
                "timestamp": int(time.time()*1000),
                "current_price": 29131.7,
                "chart_timeframe": "15",
                "levels": {
                    "monthly_high": 29520.4, "monthly_low": 28880.1,
                    "weekly_high": 29520.4, "weekly_low": 28880.1,
                    "daily_high": 29155.2, "daily_low": 28904.7,
                    "asia_high": 29123.4, "asia_low": 29001.2,
                    "london_high": 29092.3, "london_low": 28904.7,
                    "new_york_high": 29155.2, "new_york_low": 28988.9,
                    "london_close_high": 29150.1, "london_close_low": 29088.2,
                },
                "previous_completed": {"weekly_high": 29880.4, "weekly_low": 28510.3},
            }
            clean = m.save_payload(payload)
            check("exact FOREXCOM symbol locked", clean["symbol"] == "FOREXCOM:NAS100")
            check("one decimal chart price preserved", clean["current_price"] == 29131.7)

            data = {
                "nq_futures_price": 29168.25,
                "nq_liquidity": {
                    "instrument":"NQ","symbol":"NQ=F",
                    "current_price":29168.25,
                    "levels":{"monthly_high":29571.25},
                },
                "monthly_high":29571.25,
            }
            await m.apply_forexcom_chart_liquidity(None, data)
            check("chart feed primary", data["liquidity_primary_instrument"] == "FOREXCOM:NAS100")
            check("monthly level uses chart scale", data["monthly_high"] == 29520.4)
            check("chart current price exact", data["nq_liquidity"]["current_price"] == 29131.7)
            check("NQ futures price untouched", data["nq_futures_price"] == 29168.25)
            check("NQ reference preserved", data["nq_reference_liquidity"]["symbol"] == "NQ=F")
            check("wrong scale fallback blocked", data["liquidity_truth_fix"]["wrong_scale_fallback_blocked"] is True)

            m.STORE.unlink()
            data2 = {
                "nq_futures_price":29168.25,
                "monthly_high":29571.25,
                "nq_liquidity":{"instrument":"NQ","symbol":"NQ=F","levels":{"monthly_high":29571.25}},
            }
            await m.apply_forexcom_chart_liquidity(None, data2)
            check("missing sync fails closed", data2["nq_liquidity"]["levels"] == {})
            check("old NQ monthly removed from chart panel", "monthly_high" not in data2)
        finally:
            m.STORE = old_store

    print("FOREXCOM NAS100 CHART LIQUIDITY SYNC TEST PASS")

if __name__ == "__main__":
    asyncio.run(main())
