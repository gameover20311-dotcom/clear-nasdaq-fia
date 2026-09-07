import json
import re
from pathlib import Path
from collections import OrderedDict

ROOT = Path.cwd()

BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

FILES = {
    "main": BACKEND / "main.py",
    "engine": BACKEND / "fia" / "engine.py",
    "providers": BACKEND / "fia" / "providers.py",
    "models": BACKEND / "fia" / "models.py",
    "frontend_page": FRONTEND / "app" / "page.tsx",
    "frontend_alt_page": FRONTEND / "page.tsx",
    "frontend_css": FRONTEND / "app" / "globals.css",
    "frontend_pkg": FRONTEND / "package.json",
    "phase21_summary": BACKEND / "fia_backtest_phase21" / "results" / "phase21_no_neutral_backtest_1y_summary.json",
    "phase21_csv": BACKEND / "fia_backtest_phase21" / "results" / "phase21_no_neutral_backtest_1y.csv",
    "phase20_summary": BACKEND / "fia_backtest_phase20" / "results" / "phase20_full_backtest_1y_summary.json",
}

MUST_SHOW = OrderedDict([
    ("FORECAST CORE", [
        "direction",
        "bullish_probability",
        "bearish_probability",
        "confidence",
        "regime",
        "status",
        "score",
        "generated_at",
    ]),
    ("INTELLIGENCE", [
        "signals",
        "thesis",
        "bullish_evidence",
        "bearish_evidence",
        "invalidation",
        "data_coverage",
        "intelligence_coverage",
        "source_status",
    ]),
    ("MARKET", [
        "price",
        "change",
        "change_percent",
        "high",
        "low",
        "open",
        "previous_close",
        "nq_structure",
        "spx_confirmation",
        "spx_change_percent",
        "spx_price",
        "price_action",
    ]),
    ("MEGA CAPS / SEMIS / BREADTH", [
        "mega_cap",
        "mega_cap_details",
        "semis",
        "breadth",
    ]),
    ("MACRO / RATES", [
        "fed_funds_rate",
        "dxy",
        "us10y",
        "us10y_value",
        "macro",
        "macro_status",
    ]),
    ("NEWS", [
        "news",
        "news_articles",
        "news_scored_articles",
    ]),
    ("EARNINGS", [
        "earnings",
        "earnings_events",
        "earnings_surprises_counted",
        "earnings_positive",
        "earnings_negative",
        "earnings_catalyst_risk",
        "earnings_upcoming_symbols",
        "earnings_hours_to_next",
    ]),
    ("LIQUIDITY", [
        "monthly_high",
        "monthly_low",
        "weekly_high",
        "weekly_low",
        "daily_high",
        "daily_low",
        "asia_high",
        "asia_low",
        "london_high",
        "london_low",
        "new_york_high",
        "new_york_low",
        "liquidity_signal",
        "liquidity_evidence_available",
    ]),
    ("DATA HEALTH", [
        "provider_quotes_available",
        "provider_quotes_requested",
        "provider_candle_evidence",
        "provider",
        "timestamp",
    ]),
])

BACKTEST_MUST_SHOW = [
    "4H accuracy",
    "8H accuracy",
    "70%+ confidence",
    "earnings catalyst performance",
    "monthly performance",
    "prediction counts",
    "Brier score",
    "resolved sample count",
    "data quality",
    "future EPS used",
]


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def choose_frontend_page():
    if FILES["frontend_page"].exists():
        return FILES["frontend_page"]
    if FILES["frontend_alt_page"].exists():
        return FILES["frontend_alt_page"]
    return None


def extract_endpoints(text):
    return sorted(set(re.findall(r'@app\.(?:get|post)\(\s*["\']([^"\']+)', text)))


def extract_snapshot_keys(text):
    return sorted(set(re.findall(r'data\[\s*["\']([^"\']+)["\']\s*\]', text)))


def extract_forecast_fields(text):
    match = re.search(r'return\s+Forecast\s*\((.*?)\n\s*\)', text, flags=re.S)
    if not match:
        return []
    block = match.group(1)
    return sorted(set(re.findall(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', block, flags=re.M)))


def frontend_mentions(text, key):
    patterns = [
        key,
        key.replace("_", " "),
        "".join(part.capitalize() if i else part for i, part in enumerate(key.split("_"))),
    ]
    low = text.lower()
    return any(p.lower() in low for p in patterns if p)


def summarize_json(path):
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    return payload


def flatten_keys(obj, prefix=""):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.add(key)
            out |= flatten_keys(v, key)
    elif isinstance(obj, list):
        for item in obj[:3]:
            out |= flatten_keys(item, prefix)
    return out


def status_symbol(value):
    return "YES" if value else "NO"


def main():
    print("=== CLEAR NASDAQ DASHBOARD COVERAGE AUDIT ===")
    print("project_root =", ROOT)
    print()

    for name, path in FILES.items():
        if name.startswith("frontend_alt"):
            continue
        print(f"{name:20} | {'FOUND' if path.exists() else 'MISSING'} | {path}")

    page_path = choose_frontend_page()
    if not page_path:
        print("\nFATAL: no frontend page.tsx found")
        return

    main_text = read(FILES["main"])
    engine_text = read(FILES["engine"])
    provider_text = read(FILES["providers"])
    page_text = read(page_path)

    endpoints = extract_endpoints(main_text)
    snapshot_keys = set(extract_snapshot_keys(provider_text))
    forecast_fields = set(extract_forecast_fields(engine_text))

    print()
    print("=== BACKEND ENDPOINTS ===")
    for endpoint in endpoints:
        print(endpoint)

    print()
    print("=== LIVE BACKEND -> DASHBOARD COVERAGE ===")

    all_backend_keys = snapshot_keys | forecast_fields

    missing_high_priority = []

    for section, keys in MUST_SHOW.items():
        print()
        print(f"[{section}]")
        for key in keys:
            backend = key in all_backend_keys or key in provider_text or key in engine_text
            frontend = frontend_mentions(page_text, key)

            label = "OK" if backend and frontend else (
                "MISSING_ON_DASHBOARD" if backend and not frontend else
                "NOT_EXPOSED_LIVE" if not backend else
                "UNKNOWN"
            )

            print(
                f"{key:32} | backend={status_symbol(backend):3} "
                f"| dashboard={status_symbol(frontend):3} | {label}"
            )

            if backend and not frontend:
                missing_high_priority.append((section, key))

    print()
    print("=== BACKTEST ARTIFACTS ===")
    summary_path = (
        FILES["phase21_summary"]
        if FILES["phase21_summary"].exists()
        else FILES["phase20_summary"]
    )
    print("summary =", summary_path if summary_path.exists() else "MISSING")
    print("phase21 csv =", "FOUND" if FILES["phase21_csv"].exists() else "MISSING")

    summary = summarize_json(summary_path)
    if summary:
        print()
        print("=== BACKTEST SUMMARY KEY SAMPLE ===")
        if isinstance(summary, dict) and "error" not in summary:
            keys = sorted(flatten_keys(summary))
            for key in keys[:120]:
                print(key)
        else:
            print(summary)

    print()
    print("=== DASHBOARD TARGET CHECKLIST ===")
    for item in BACKTEST_MUST_SHOW:
        present = frontend_mentions(page_text, item)
        print(f"{item:32} | dashboard={status_symbol(present)}")

    print()
    print("=== IMPORTANT GAPS ===")
    if missing_high_priority:
        seen = set()
        for section, key in missing_high_priority:
            pair = (section, key)
            if pair in seen:
                continue
            seen.add(pair)
            print(f"{section} -> {key}")
    else:
        print("No obvious backend fields missing from dashboard by static scan.")

    print()
    print("=== UPCOMING CATALYST CHECK ===")
    upcoming_fields = [
        "earnings_upcoming_symbols",
        "earnings_hours_to_next",
        "earnings_catalyst_risk",
    ]
    for key in upcoming_fields:
        live_exposed = key in provider_text
        engine_aware = key in engine_text
        print(
            f"{key:28} | provider_live={status_symbol(live_exposed)} "
            f"| engine_aware={status_symbol(engine_aware)}"
        )

    print()
    print("=== RECOMMENDED DASHBOARD SECTIONS ===")
    sections = [
        "1. FIA Live Forecast",
        "2. Confidence + Regime + Coverage",
        "3. Top Bullish / Bearish Evidence",
        "4. Signal Breakdown",
        "5. Mega-cap Leadership",
        "6. Semiconductors + Breadth",
        "7. NQ Liquidity Map + Sweeps/Reclaims",
        "8. Macro / Rates / DXY",
        "9. News Intelligence",
        "10. Upcoming Earnings / Catalysts",
        "11. Risk + Invalidation",
        "12. Provider / Data Health",
        "13. Phase 21 Backtest Scorecard",
        "14. Monthly Backtest Performance",
        "15. Confidence Accuracy",
        "16. Earnings-Day vs Other-Day Performance",
    ]
    for s in sections:
        print(s)

    print()
    print("frontend_page =", page_path)
    print("=== DASHBOARD COVERAGE AUDIT COMPLETE ===")


if __name__ == "__main__":
    main()
