from pathlib import Path
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path: sys.path.insert(0, str(_BACKEND))

from fia.nq_liquidity_truth import previous_completed_periods, latest_completed_sessions
from fia.liquidity import build_liquidity_groups, build_liquidity_map
NY = ZoneInfo("America/New_York")

def check(name, cond, detail=None):
    if not cond: raise AssertionError(f"{name} FAIL {detail}")
    print("PASS", name)

def main():
    # Anchor = Sep 2. Previous day=Sep1, previous week=Aug24 week, previous month=Aug.
    daily = [
        {"date": date(2026,8,28), "high": 28800.00, "low": 28400.00},
        {"date": date(2026,8,31), "high": 29050.00, "low": 28750.00},
        {"date": date(2026,9,1), "high": 29125.00, "low": 28875.25},
        {"date": date(2026,9,2), "high": 29200.00, "low": 28950.00},
    ]
    p = previous_completed_periods(daily)
    levels=p["levels"]
    check("previous month high exact", levels["monthly_high"] == 29050.0, p)
    check("previous month low exact", levels["monthly_low"] == 28400.0, p)
    check("previous week high exact", levels["weekly_high"] == 28800.0, p)
    check("previous week low exact", levels["weekly_low"] == 28400.0, p)
    check("previous day high exact", levels["daily_high"] == 29125.0, p)
    check("NQ tick quantization", levels["daily_low"] == 28875.25, p)
    check("period origin explicit", p["origin"]["daily"] == "2026-09-01", p)

    rows = [
        {"datetime": datetime(2026,9,1,20,0,tzinfo=NY), "high":28900,"low":28850},
        {"datetime": datetime(2026,9,1,23,55,tzinfo=NY), "high":29000,"low":28800},
        {"datetime": datetime(2026,9,2,3,0,tzinfo=NY), "high":29020,"low":28920},
        {"datetime": datetime(2026,9,2,4,55,tzinfo=NY), "high":29080,"low":28900},
        {"datetime": datetime(2026,9,2,7,55,tzinfo=NY), "high":29080,"low":28980},
        {"datetime": datetime(2026,9,2,9,30,tzinfo=NY), "high":29090,"low":28980},
        {"datetime": datetime(2026,9,2,11,55,tzinfo=NY), "high":29125,"low":28950},
        # Outside the documented 07:00-12:00 New York window; must not affect the session.
        {"datetime": datetime(2026,9,2,15,55,tzinfo=NY), "high":29999,"low":28000},
    ]
    s = latest_completed_sessions(rows, now=datetime(2026,9,2,17,0,tzinfo=NY))
    sl=s["levels"]
    check("Asia completed window exact", sl["asia_high"] == 29000.0 and sl["asia_low"] == 28800.0, s)
    check("London completed window exact", sl["london_high"] == 29080.0 and sl["london_low"] == 28900.0, s)
    check("New York completed window exact", sl["new_york_high"] == 29125.0 and sl["new_york_low"] == 28950.0, s)

    data = {
        "price": 602.0, "nq_futures_price": 29000.0,
        "qqq_liquidity": {"current_price":602.0,"levels":{"monthly_high":610.0,"monthly_low":580.0,"weekly_high":605.0,"weekly_low":590.0,"daily_high":603.0,"daily_low":596.0},"source":"QQQ"},
        "nq_liquidity": {"current_price":29000.0,"levels":{**levels, **sl},"level_status":{**p["status"], **s["status"]},"source":"NQ=F"},
    }
    g=build_liquidity_groups(data)
    check("NQ is primary/first", next(iter(g)) == "nq")
    check("NQ monthly uses NQ scale", g["nq"]["levels"]["monthly_high"].price == 29050.0)
    check("QQQ remains separate reference", g["qqq"]["levels"]["monthly_high"].price == 610.0)
    flat=build_liquidity_map(data)
    check("flat monthly resolves to NQ", flat["monthly_high"].instrument == "NQ" and flat["monthly_high"].price == 29050.0)
    # providers.py was split three ways by responsibility, so the provider layer is
    # now a facade plus three mixin modules. Reading providers.py alone would look
    # at 58 lines of imports and silently stop finding wiring that is still there.
    # Read the whole layer instead; the assertion below is unchanged.
    providers="".join((_BACKEND/"fia"/_m).read_text(encoding="utf-8")
                      for _m in ("providers.py", "providers_model.py", "providers_protocol.py",
              "providers_infrastructure.py"))
    check("snapshot truth fix wired", "LIQUIDITY_TRUTH_FIX_V1" in providers and "apply_nq_chart_liquidity" in providers)
    print("LIQUIDITY TRUTH FIX TEST PASS")

if __name__ == "__main__": main()
