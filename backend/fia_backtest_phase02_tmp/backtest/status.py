from datetime import datetime, timezone

BUILD_STATUS = {
    "module": "FIA BACKTEST LAB",
    "version": "0.2.0",
    "phase": "02 — Historical FIA Replay",
    "state": "IN_PROGRESS",
    "current_capability": (
        "Replays timestamped historical FIA snapshots through the supplied "
        "forecast function with explicit look-ahead guards."
    ),
    "completed": [
        "Phase-1 run/data schemas retained",
        "JSONL/CSV historical snapshot loader",
        "Timestamp ordering",
        "As-of timestamp validation",
        "Source timestamp look-ahead guard",
        "Historical forecast replay adapter",
        "Prediction record generation",
        "Data-quality/provider evidence capture",
    ],
    "not_yet_active": [
        "Automatic historical provider download",
        "4H/8H outcome calculation",
        "Accuracy calculation",
        "Probability calibration",
        "Regime analysis",
        "Walk-forward testing",
        "Backtest dashboard",
    ],
    "next_phase": "03 — Future Outcome Engine",
}


def get_status():
    return {**BUILD_STATUS, "updated_at": datetime.now(timezone.utc).isoformat()}
