"""Run existing active scripts in disposable storage, retaining failed gates.

This executes the repository's script-style regressions and existing brain
runner. It is not a predictive evaluation. Historical archives are not active
suites. All writes by legacy scripts land in a temporary copy; no result files
or production credentials are imported back into the working tree.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-tree", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failure-list", type=Path)
    args = parser.parse_args()
    source, output = args.source_tree.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.failure_list:
        previous = json.loads(args.failure_list.read_text())
        tests = [Path(row["path"]) for row in previous if row["result"] != "PASS"]
    else:
        tests = []
        separate = {"test_live_integrity_postgres_v673.py", "test_live_integrity_app_v673.py"}
        for path in (source / "backend").rglob("*.py"):
            rel = path.relative_to(source / "backend")
            if any("archive" in part.lower() or "backup" in part.lower() for part in rel.parts):
                continue
            if rel.parts[:2] == ("clear_nasdaq_brain", "tests") or path.name in separate:
                continue
            if path.name.startswith("test_") or path.name.endswith("_test.py"):
                tests.append(rel)
        tests.sort()
        tests.append(Path("clear_nasdaq_brain/tests/run_all.py"))
    if any(rel.is_absolute() or ".." in rel.parts for rel in tests):
        raise ValueError("Test paths must stay inside the copied backend")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    results = []
    with tempfile.TemporaryDirectory(prefix="fia_TEST_regressions_") as directory:
        root = Path(directory)
        ignored = shutil.ignore_patterns("__pycache__", ".env", ".env.*", "node_modules", ".next", "pr6-test-results")
        for part in ("backend", "frontend"):
            shutil.copytree(source / part, root / part, ignore=ignored)
        backend = root / "backend"
        env = dict(os.environ)
        env.update(DATABASE_URL="", FIA_FORWARD_OOS_ENABLED="0", FIA_ALLOW_LIVE_HISTORICAL_REFETCH="0",
                   PYTHONPATH=str(backend) + os.pathsep + str(backend / "clear_nasdaq_brain"),
                   CLEAR_NASDAQ_AUTH_STATE_DIR=str(root / "auth"),
                   CLEAR_NASDAQ_AUTH_DB_PATH=str(root / "auth.sqlite"),
                   CLEAR_NASDAQ_AUTH_SECRET_FILE=str(root / "auth-secret"))
        for rel in tests:
            start = time.monotonic()
            try:
                completed = subprocess.run([sys.executable, str(rel)], cwd=backend, env=env,
                                           text=True, capture_output=True,
                                           timeout=600 if rel.name == "run_all.py" else 180)
                content = completed.stdout + completed.stderr
                code = completed.returncode
                status = "PASS" if code == 0 and content.strip() else ("FAIL" if code else "NOT TESTED")
            except subprocess.TimeoutExpired as error:
                def decode(value):
                    return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
                content = decode(error.stdout) + decode(error.stderr) + "\nTIMEOUT: test did not complete\n"
                code, status = 124, "NOT TESTED"
            filename = str(rel).replace("/", "__") + ".log"
            (output / filename).write_text(content)
            row = {"path": str(rel), "result": status, "exit_code": code,
                   "seconds": round(time.monotonic() - start, 2), "log": filename}
            results.append(row)
            (output / "results.json").write_text(json.dumps(results, indent=2))
            print(json.dumps(row), flush=True)
    counts = {key: sum(row["result"] == key for row in results) for key in ("PASS", "FAIL", "NOT TESTED")}
    summary = {"source_commit": revision, "completed": len(results), "counts": counts,
               "production_modified": False, "test_storage": "DISPOSABLE_COPY_WITH_FRONTEND"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    return 0 if results and all(row["result"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
