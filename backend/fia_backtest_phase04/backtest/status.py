from datetime import datetime, timezone


def build_status():
    return {
        "phase": 4,
        "name": "Accuracy + Metrics",
        "status": "complete",
        "current_capability": "Measures joined FIA predictions against historical 4H/8H outcomes.",
        "completed": [
            "4H/8H directional accuracy",
            "Correct/wrong counts",
            "Average forward return",
            "Average MFE/MAE",
            "Bullish-probability Brier score",
            "Confidence bucket analysis",
        ],
        "not_yet_active": [
            "Probability calibration curves",
            "Regime analysis",
            "Session analysis",
            "Signal attribution and ablation",
            "Walk-forward validation",
            "Out-of-sample final test",
            "Dashboard integration",
        ],
        "next": "Phase 5 — Probability Calibration",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
