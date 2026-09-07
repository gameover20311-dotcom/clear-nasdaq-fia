from pathlib import Path

from fia_backtest_phase12.backtest.dashboard import (
    build_dashboard,
    render_text,
)
from fia_backtest_phase12.backtest.storage import DashboardStorage


def main():
    root = Path.cwd()

    dashboard = build_dashboard(root)

    print(render_text(dashboard))

    output_dir = root / "fia_backtest_phase12" / "output"
    storage = DashboardStorage(output_dir)

    storage.write_json("final_dashboard", dashboard)
    storage.write_text(
        "final_dashboard",
        render_text(dashboard),
    )

    print("")
    print("Dashboard report generated.")


if __name__ == "__main__":
    main()
