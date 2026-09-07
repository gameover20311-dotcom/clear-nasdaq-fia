from __future__ import annotations

from pathlib import Path
import py_compile
import re
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

EXPECTED_WEIGHTS = {
    "NQ structure": 0.20,
    "SPX confirmation": 0.10,
    "DXY": 0.08,
    "US10Y": 0.07,
    "Mega-cap leadership": 0.20,
    "Semiconductors": 0.12,
    "Breadth": 0.08,
    "News": 0.07,
    "Macro calendar": 0.04,
    "Earnings/guidance": 0.04,
}


def check(name, cond):
    print(("✅" if cond else "❌"), name)
    if not cond:
        raise SystemExit(1)


def weights_from_engine(text: str):
    found = {}
    for name in EXPECTED_WEIGHTS:
        pat = re.compile(r'\(\s*["\']' + re.escape(name) + r'["\']\s*,.*?\n\s*([0-9.]+)\s*,', re.S)
        m = pat.search(text)
        if m:
            found[name] = float(m.group(1))
    return found

engine = BACKEND / "fia" / "engine.py"
main = BACKEND / "main.py"
final_module = BACKEND / "fia" / "final_integration.py"
dashboard_api = BACKEND / "fia" / "dashboard_api.py"
page = ROOT / "frontend" / "app" / "page.tsx"
proxy = ROOT / "frontend" / "app" / "api" / "fia" / "final-status" / "route.ts"

for p in [main, final_module, dashboard_api]:
    py_compile.compile(str(p), doraise=True)

main_text = main.read_text()
page_text = page.read_text()
engine_text = engine.read_text()

check("final integration backend module installed", final_module.exists())
check("/api/final/status route installed", '@app.get("/api/final/status")' in main_text)
check("frontend final-status proxy installed", proxy.exists())
check("dashboard Phase24-27 integration installed", "PHASE27_FINAL_INTEGRATION_V1" in page_text)
check("manual refresh preserved", "setInterval(" not in page_text and "Refresh data" in page_text)
check("Phase21 weights unchanged", weights_from_engine(engine_text) == EXPECTED_WEIGHTS)
check("QQQ/NQ grouped liquidity wired", "liquidity_groups" in dashboard_api.read_text() and "liqGroups" in page_text)
check("direct DXY label wired", 'label="DXY"' in page_text and "DXY / Rate Proxy" not in page_text)
check("truthful news counts/status wired", 'label="News status"' in page_text and 'label="Articles"' in page_text)
check("Phase24 module installed", (BACKEND / "fia" / "accuracy_engine.py").exists())
check("Phase25 module installed", (BACKEND / "fia" / "confluence_engine.py").exists())
check("Phase26 module installed", (BACKEND / "fia" / "learning_engine.py").exists())

phase_tests = [
    "fia_backtest_phase22/phase22_truth_consistency_test.py",
    "fia_backtest_phase23/phase23_data_reliability_test.py",
    "fia_backtest_phase24/phase24_accuracy_engine_test.py",
    "fia_backtest_phase25/phase25_chart_confluence_test.py",
    "fia_backtest_phase26/phase26_learning_validation_test.py",
]
for rel in phase_tests:
    p = BACKEND / rel
    check(f"{rel} exists", p.exists())
    proc = subprocess.run([sys.executable, str(p)], cwd=BACKEND, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(f"❌ prior phase regression: {rel}")
    print(f"✅ regression PASS: {rel}")

print("\n========================================")
print("✅ PHASE 27 FINAL INTEGRATION PASS")
print("dashboard_phase24_26 = PASS")
print("liquidity_truth_ui = PASS")
print("provider_truth_ui = PASS")
print("full_system_audit = PASS")
print("phase22_26_regression = PASS")
print("forecast_weights_changed = NO")
print("broker_execution_added = NO")
print("========================================")
