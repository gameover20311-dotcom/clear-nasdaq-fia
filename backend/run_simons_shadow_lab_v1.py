#!/usr/bin/env python3
"""CLI for SIMONS SHADOW LAB V1.

This executable reads production Forward-OOS evidence and writes only under the
separate lab root supplied by the caller.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from simons_shadow_lab_v1.lab import ShadowLab, discover_threshold_grid


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description="SIMONS SHADOW LAB V1")
    parser.add_argument("--source-root", default="fia_forward_oos")
    parser.add_argument("--lab-root", default="simons_shadow_lab_data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("snapshot")
    d = sub.add_parser("discover")
    d.add_argument("--snapshot-id", required=True)
    d.add_argument("--min-n", type=int, default=12)
    r = sub.add_parser("report")
    r.add_argument("--candidate-id", required=True)
    args = parser.parse_args()

    lab = ShadowLab(Path(args.source_root), Path(args.lab_root))
    if args.command == "audit":
        emit(lab.audit_source())
    elif args.command == "snapshot":
        emit(lab.create_snapshot())
    elif args.command == "discover":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = discover_threshold_grid(rows, min_n=args.min_n)
        result["snapshot_id"] = manifest["snapshot_id"]
        emit(result)
    elif args.command == "report":
        emit(lab.candidate_report(args.candidate_id))


if __name__ == "__main__":
    main()
