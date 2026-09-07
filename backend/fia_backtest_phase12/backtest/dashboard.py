import json
from pathlib import Path
from typing import Any, Dict


PHASES = {
    1: ("Historical Data Foundation", "fia_backtest_module"),
    2: ("Historical FIA Replay", "fia_backtest_phase02_tmp"),
    3: ("Future Outcome Engine", "fia_backtest_phase03"),
    4: ("Accuracy + Metrics", "fia_backtest_phase04"),
    5: ("Probability Calibration", "fia_backtest_phase05"),
    6: ("Regime Analysis", "fia_backtest_phase06"),
    7: ("Session Analysis", "fia_backtest_phase07"),
    8: ("Signal Attribution", "fia_backtest_phase08"),
    9: ("Ablation Testing", "fia_backtest_phase09"),
    10: ("Walk-Forward Validation", "fia_backtest_phase10"),
    11: ("Out-of-Sample Validation", "fia_backtest_phase11"),
    12: ("Final Dashboard", "fia_backtest_phase12"),
}


def load_status(root: Path, directory: str):
    path = root / directory / "status.json"

    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_dashboard(root) -> Dict[str, Any]:
    root = Path(root)

    phase_rows = []

    for phase, (name, directory) in PHASES.items():
        status = load_status(root, directory)

        phase_rows.append({
            "phase": phase,
            "name": name,
            "directory": directory,
            "status": (
                status.get("status")
                if status else "not_found"
            ),
        })

    return {
        "module": "FIA Backtest Lab",
        "dashboard": "Final Dashboard",
        "phases": phase_rows,
        "historical_data_available": False,
        "real_performance_available": False,
        "warning": (
            "No historical prediction/outcome dataset was found. "
            "Performance values must not be fabricated."
        ),
    }


def render_text(dashboard: Dict[str, Any]) -> str:
    lines = [
        "FIA BACKTEST LAB — FINAL DASHBOARD",
        "=" * 40,
        "",
    ]

    for row in dashboard["phases"]:
        lines.append(
            f"Phase {row['phase']:02d} | "
            f"{row['name']} | "
            f"{row['status']}"
        )

    lines.extend([
        "",
        f"Historical data available: "
        f"{dashboard['historical_data_available']}",
        f"Real performance available: "
        f"{dashboard['real_performance_available']}",
        "",
        "WARNING:",
        dashboard["warning"],
    ])

    return "\n".join(lines)
