from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.nq_liquidity_truth import previous_completed_periods, latest_completed_sessions
from fia.liquidity import build_liquidity_groups

NY = ZoneInfo("America/New_York")

def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print("PASS", name)

daily = [
    {"date": datetime(2026,7,31).date(), "high": 28000, "low": 27000},
    {"date": datetime(2026,8,3).date(), "high": 28200, "low": 27500},
    {"date": datetime(2026,8,31).date(), "high": 29500, "low": 28000},
    {"date": datetime(2026,9,1).date(), "high": 29600, "low": 29000},
    {"date": datetime(2026,9,2).date(), "high": 29400, "low": 28800},
]
p = previous_completed_periods(daily)
check("previous day is Sep 1", p["origin"]["daily"] == "2026-09-01")
check("PDH is prior day, not current day", p["levels"]["daily_high"] == 29600.0)
check("previous month is August", p["origin"]["monthly"] == "2026-08")
check("PMH excludes current September", p["levels"]["monthly_high"] == 29500.0)
check("PMH tapped after month close", p["status"]["monthly_high"] == "TAPPED")

rows = []
def add(dt, h, l):
    rows.append({"datetime": dt, "date": dt.date(), "high": h, "low": l, "close": (h+l)/2})

# Asia session for Sep 2 = Sep 1 20:00 -> Sep 2 00:00
for hh, h, l in [(20,29100,29050),(21,29120,29060),(22,29110,29040),(23,29130,29070)]:
    add(datetime(2026,9,1,hh,30,tzinfo=NY), h, l)
# Later price taps Asia high.
add(datetime(2026,9,2,1,0,tzinfo=NY), 29140, 29080)
# London 02-05
add(datetime(2026,9,2,2,30,tzinfo=NY), 29100, 29000)
add(datetime(2026,9,2,4,30,tzinfo=NY), 29110, 28990)
# New York 07-12
add(datetime(2026,9,2,7,30,tzinfo=NY), 29150, 29020)
add(datetime(2026,9,2,11,30,tzinfo=NY), 29160, 29010)

s = latest_completed_sessions(rows, now=datetime(2026,9,2,13,0,tzinfo=NY))
check("Asia exact 20-00 window", s["levels"]["asia_high"] == 29130.0)
check("Asia high tap detected", s["status"]["asia_high"] == "TAPPED")
check("London exact 02-05 window", s["levels"]["london_low"] == 28990.0)
check("New York exact 07-12 window", s["levels"]["new_york_high"] == 29160.0)

data = {
    "nq_liquidity": {
        "symbol": "NQU6",
        "current_price": 29100.0,
        "levels": {"daily_high": 29600.0, "daily_low": 29000.0},
        "level_status": {"daily_high": "UNTAPPED", "daily_low": "TAPPED"},
        "source": "Polygon/Massive explicit NQ contract NQU6",
        "note": "NQ futures scale.",
    },
    "qqq_liquidity": {"current_price": 700.0, "levels": {}, "level_status": {}},
}
g = build_liquidity_groups(data)
check("real status not hard-coded", g["nq"]["levels"]["daily_low"].status == "TAPPED")
check("untapped preserved", g["nq"]["levels"]["daily_high"].status == "UNTAPPED")
check("explicit contract visible", g["nq"]["symbol"] == "NQU6")

print("ZERO COST AUTONOMOUS LIQUIDITY TEST PASS")
