# CLEAR NASDAQ — FIA (Phase 29 Authenticity Foundation)

All-in-one NASDAQ-100 intelligence architecture.

Pipeline:
Market data + index/ETF confirmation + DXY + US10Y + mega-cap leadership + semiconductors + breadth + news + economic calendar + earnings/guidance -> normalized signals -> weighted FIA score -> probability/confidence/regime -> dashboard.

Important: this package is a research intelligence/forecast system, not an
order-execution system and not a guarantee of future performance. Live status
requires configured data providers/API keys. Without them the API explicitly
reports DEGRADED/DEMO rather than pretending data is live.

## Authenticity status

Phase 29 rejects the old Phase 28 100% accuracy display. The old metric removed
every `False` outcome from its denominator. The raw legacy CSV actually contains
115 correct / 249 resolved forecasts at 4H and 91 correct / 200 resolved at 8H.

The upgraded replay now uses completed Massive NQ 5-minute bars on a frozen
entry-time contract, counts both wins and losses, exposes outcome provenance,
detects chart features independently of forecast direction, and fails its hard
truth gate on low outcome coverage or suspicious perfect results. Forecast
weights were not changed.

## Environment
Copy `.env.example` to `.env` and add provider credentials as available. The engine is provider-agnostic and includes safe fallback behavior.

## Run
Use two Terminal windows on macOS.

Backend:

```bash
cd ~/Downloads/clear_nasdaq_fia-2/backend
source .venv/bin/activate
set -a
source .env
set +a
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Frontend:

```bash
cd ~/Downloads/clear_nasdaq_fia-2/frontend
npm run dev
```

Keep both Terminal windows running while using the dashboard. Open
`http://localhost:3000`. Press `Control+C` in each window when finished.

Phase 29 verification from `backend`:

```bash
python fia_backtest_phase29/phase29_truth_test.py
python fia_backtest_phase29/phase29_revalidate_predictions.py
```
