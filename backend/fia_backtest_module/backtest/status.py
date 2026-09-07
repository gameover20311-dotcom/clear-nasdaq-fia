from datetime import datetime, timezone

BUILD_STATUS = {
    "module": "FIA BACKTEST LAB",
    "version": "0.1.0",
    "phase": "01 — Historical Data Foundation",
    "state": "IN_PROGRESS",
    "current_capability": (
        "Defines timestamped historical prediction/input/outcome schemas "
        "and validates backtest run configuration."
    ),
    "completed": [
        "Backtest run manifest schema",
        "Historical observation schema",
        "Prediction record schema",
        "Outcome record schema",
        "Data-quality tracking fields",
        "Look-ahead-bias guard configuration",
    ],
    "not_yet_active": [
        "Historical FIA replay",
        "4H/8H outcome calculation",
        "Accuracy calculation",
        "Probability calibration",
        "Regime analysis",
        "Walk-forward testing",
        "Backtest dashboard",
    ],
    "next_phase": "02 — Historical FIA Replay",
}


def get_status():
    return {
        **BUILD_STATUS,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
