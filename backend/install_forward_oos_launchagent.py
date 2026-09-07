#!/usr/bin/env python3
"""Install the CLEAR NASDAQ Forward OOS daemon as a per-user macOS LaunchAgent."""
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.clearnasdaq.forwardoos"
BACKEND = Path(__file__).resolve().parent
DAEMON = BACKEND / "run_forward_oos_daemon.py"
LOG_DIR = BACKEND / "fia_forward_oos" / "logs"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def choose_python() -> Path:
    local = BACKEND / ".venv" / "bin" / "python"
    if local.exists():
        return local.resolve()
    return Path(sys.executable).resolve()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Write/validate plist but do not call launchctl")
    args = ap.parse_args()
    python = choose_python()
    if not DAEMON.exists():
        raise SystemExit(f"Missing daemon: {DAEMON}")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(DAEMON)],
        "WorkingDirectory": str(BACKEND),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(LOG_DIR / "forward_oos.out.log"),
        "StandardErrorPath": str(LOG_DIR / "forward_oos.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "FIA_FORWARD_OOS_ENABLED": os.getenv("FIA_FORWARD_OOS_ENABLED", "1"),
            "FIA_FORWARD_OOS_CHECKPOINT_ET": os.getenv("FIA_FORWARD_OOS_CHECKPOINT_ET", "13:00"),
            "FIA_FORWARD_OOS_GRACE_MINUTES": os.getenv("FIA_FORWARD_OOS_GRACE_MINUTES", "10"),
            "FIA_FORWARD_OOS_POLL_SECONDS": os.getenv("FIA_FORWARD_OOS_POLL_SECONDS", "60"),
            "FIA_FORWARD_OOS_REQUIRE_EXPLICIT_CONTRACT": "1",
        },
    }
    with PLIST.open("wb") as f:
        plistlib.dump(payload, f, sort_keys=True)
    # Round-trip parse proves plist syntax before launchctl touches it.
    with PLIST.open("rb") as f:
        parsed = plistlib.load(f)
    if parsed.get("Label") != LABEL or parsed.get("ProgramArguments") != [str(python), str(DAEMON)]:
        raise SystemExit("LaunchAgent plist validation failed")
    if args.dry_run:
        print("✅ CLEAR NASDAQ Forward OOS LaunchAgent DRY-RUN PASS")
        print("plist =", PLIST)
        print("python =", python)
        print("daemon =", DAEMON)
        return

    uid = os.getuid()
    domain = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], check=True)
    subprocess.run(["launchctl", "enable", f"{domain}/{LABEL}"], check=False)
    subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=False)
    print("✅ CLEAR NASDAQ Forward OOS LaunchAgent installed")
    print("plist =", PLIST)
    print("python =", python)
    print("daemon =", DAEMON)
    print("logs =", LOG_DIR)
    print("No historical backfill. Next eligible 13:00 ET checkpoint will be locked automatically.")


if __name__ == "__main__":
    main()
