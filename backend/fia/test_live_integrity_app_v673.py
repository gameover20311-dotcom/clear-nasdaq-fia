"""Actual Uvicorn/FastAPI HTTP test in a disposable full backend copy.

Uses the preserved damaged V6 event as an immutable test fixture, never as new
forward evidence. The real app, routes and providers run without handler mocks.
The automatic collector is disabled; no production connection is permitted.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main():
    output = Path(os.getenv("FIA_TEST_OUTPUT_DIR", "pr6-test-results")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"mode": "ACTUAL_FASTAPI_HTTP", "production_modified": False,
              "providers_mocked": False, "collector_enabled": False, "endpoints": []}
    schema = None
    process = None
    with tempfile.TemporaryDirectory(prefix="fia_TEST_app_") as temp:
        root = Path(temp)
        backend = root / "backend"
        shutil.copytree(BACKEND, backend, ignore=shutil.ignore_patterns("__pycache__", ".env", ".env.*", "pr6-test-results"))
        ledger = backend / "fia_forward_oos"
        archive = ledger / "V6_UNVERIFIED_ARCHIVE_20260911"
        for folder in ("events", "evidence"):
            shutil.rmtree(ledger / folder, ignore_errors=True)
            (ledger / folder).mkdir()
        (ledger / "LEDGER_HEAD.json").unlink(missing_ok=True)
        event_path = next((archive / "events").glob("*.json"))
        event_bytes = event_path.read_bytes()
        shutil.copyfile(event_path, ledger / "events" / event_path.name)
        shutil.copyfile(archive / "FORWARD_OOS_CAMPAIGN_SEAL.json", ledger / "FORWARD_OOS_CAMPAIGN_SEAL.json")
        report["fixture_event_sha256"] = hashlib.sha256(event_bytes).hexdigest()
        env = dict(os.environ)
        env.update(DATABASE_URL="", FIA_FORWARD_OOS_ENABLED="0",
                   CLEAR_NASDAQ_AUTH_STATE_DIR=str(root / "auth"),
                   CLEAR_NASDAQ_AUTH_DB_PATH=str(root / "auth.sqlite3"),
                   CLEAR_NASDAQ_AUTH_SECRET_FILE=str(root / "auth_secret"))
        if os.getenv("FIA_TEST_POSTGRES_DSN"):
            import psycopg
            from psycopg import sql
            from psycopg.conninfo import make_conninfo
            from fia.test_live_integrity_postgres_v673 import isolated_dsn
            from fia.forward_oos_durable import _SCHEMA
            base_dsn = isolated_dsn()
            schema = "fia_pr6_api_" + uuid.uuid4().hex
            with psycopg.connect(base_dsn, autocommit=True) as conn:
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            env["DATABASE_URL"] = make_conninfo(base_dsn, options="-c search_path=" + schema)
            event = json.loads(event_bytes)
            with psycopg.connect(env["DATABASE_URL"]) as conn:
                for ddl in _SCHEMA[:3]:
                    conn.execute(ddl)
                conn.execute("INSERT INTO forward_oos_events (campaign_id,seq,event_type,forecast_id,created_at_utc,prev_event_hash,event_hash,file_name,canonical_json,is_test) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)",
                             ("CLEAR-NASDAQ-FORWARD-OOS-V6-V672", event["seq"], event["event_type"], event["forecast_id"], event["created_at_utc"], event["prev_event_hash"], event["event_hash"], event_path.name, event_bytes))
            report["database"] = "ISOLATED_REAL_POSTGRES_18"
        else:
            report["database"] = "NO_POSTGRES_LOCAL_EPHEMERAL"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        address = "http://127.0.0.1:%s" % port
        try:
            with (output / "app-server.log").open("w") as logs:
                process = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=backend, env=env, stdout=logs, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("APP_STARTUP_FAILED")
                    try:
                        with urllib.request.urlopen(address + "/api/health", timeout=1):
                            break
                    except Exception:
                        time.sleep(0.25)
                else:
                    raise RuntimeError("APP_STARTUP_TIMEOUT")
                predicates = {
                    "/api/health": lambda d: d.get("ok") is True,
                    "/api/forward-oos/verify": lambda d: d.get("ok") is False and d.get("forecast_locks") == 1,
                    "/api/forward-oos/campaign": lambda d: d.get("operational_ok") is False and d.get("ledger_ok") is False and d.get("directional_n") == 1 and d.get("verified_directional_n") == 0 and d.get("metrics_available") is False,
                    "/api/forward-oos/records": lambda d: d.get("records_verified") is False and len(d.get("records", [])) == 1,
                    "/api/forward-oos/durability": lambda d: d.get("durable") is False and d.get("durability") != "DURABLE",
                    "/api/forward-oos/report": lambda d: d.get("ok") is False and d.get("stage") == "BLOCKED_LEDGER_INTEGRITY",
                    "/api/final/status": lambda d: d.get("overall") != "PASS" and d.get("checks", {}).get("forward_oos_operational") is False,
                    "/api/final/dashboard": lambda d: d.get("final_cockpit", {}).get("system_status") != "READY" and d.get("forward_oos_campaign", {}).get("ledger_ok") is False and d.get("forward_oos_campaign", {}).get("verified_directional_n") == 0,
                }
                for path, predicate in predicates.items():
                    result = {"path": path, "result": "FAIL"}
                    try:
                        with urllib.request.urlopen(address + path, timeout=90) as response:
                            result["http_status"] = response.status
                            payload = json.loads(response.read())
                        name = path.strip("/").replace("/", "_") + ".json"
                        (output / name).write_text(json.dumps(payload, indent=2))
                        result["result"] = "PASS" if predicate(payload) else "FAIL"
                    except Exception as exc:
                        result["error_type"] = type(exc).__name__
                    report["endpoints"].append(result)
                    print(json.dumps(result), flush=True)
                report["fixture_unchanged"] = (ledger / "events" / event_path.name).read_bytes() == event_bytes
                report["missing_proofs_not_created"] = not (ledger / "evidence" / "NQ-FOOS-20260909.json").exists() and not (ledger / "LEDGER_HEAD.json").exists()
                report["result"] = "PASS" if all(item["result"] == "PASS" for item in report["endpoints"]) and report["fixture_unchanged"] and report["missing_proofs_not_created"] else "FAIL"
        except Exception as exc:
            report.update(result="FAIL", error_type=type(exc).__name__, error=str(exc))
        finally:
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            if schema:
                with psycopg.connect(base_dsn, autocommit=True) as conn:
                    conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            (output / "app-e2e.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report.get("result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
