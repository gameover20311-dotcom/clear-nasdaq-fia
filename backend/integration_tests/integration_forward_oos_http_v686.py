"""V6.8.6 — actual Uvicorn/FastAPI + isolated Postgres OOS integration.

Runs the real app from a disposable backend copy. No handler mocks, no
production DB, no production filesystem writes. It proves public read routes
fail closed and HTTP scientific mutations require BOTH membership and the
independent operation secret. A successful mutation uses only the dedicated
is_test durability fixture and is deleted before the schema is dropped.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from integration_tests.integration_forward_oos_postgres_v686 import isolated_dsn

BACKEND = Path(__file__).resolve().parents[1]
SCIENCE_SECRET = "v686-scientific-operation-secret-0123456789abcdef"
AUTH_SECRET = "v686-auth-signing-secret-0123456789abcdef-0001"


def request_json(base, path, *, method="GET", body=None, headers=None, timeout=30):
    raw = None if body is None else json.dumps(body).encode("utf-8")
    final_headers = {"Accept": "application/json", **(headers or {})}
    if raw is not None:
        final_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=raw, headers=final_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            return response.status, json.loads(data or b"{}")
    except urllib.error.HTTPError as exc:
        data = exc.read()
        try:
            payload = json.loads(data or b"{}")
        except Exception:
            payload = {"raw": data.decode("utf-8", errors="replace")}
        return exc.code, payload


def require(checks, name, condition, detail=None):
    item = {"name": name, "pass": bool(condition)}
    if detail is not None:
        item["detail"] = detail
    checks.append(item)
    print(("PASS" if condition else "FAIL"), name, "" if detail is None else detail, flush=True)


def main() -> int:
    output = Path(os.getenv("FIA_TEST_OUTPUT_DIR", "v686-test-results")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    report = {
        "schema": "FIA_V686_REAL_HTTP_POSTGRES",
        "mode": "ACTUAL_UVICORN_FASTAPI_ISOLATED_POSTGRES",
        "production_modified": False,
        "handlers_mocked": False,
        "collector_enabled": False,
        "checks": checks,
    }

    base_dsn = isolated_dsn()
    schema = "fia_v686_http_" + uuid.uuid4().hex
    process = None
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    dsn = make_conninfo(base_dsn, options="-c search_path=" + schema)

    try:
        with tempfile.TemporaryDirectory(prefix="fia_TEST_v686_http_") as temp:
            temp_root = Path(temp)
            backend = temp_root / "backend"
            shutil.copytree(
                BACKEND,
                backend,
                ignore=shutil.ignore_patterns("__pycache__", ".env", ".env.*", "v686-test-results", "pr6-test-results"),
            )
            ledger = backend / "fia_forward_oos"
            shutil.rmtree(ledger, ignore_errors=True)
            (ledger / "events").mkdir(parents=True)
            (ledger / "evidence").mkdir(parents=True)
            (ledger / "FORWARD_OOS_CAMPAIGN_SEAL.json").write_text(
                '{"campaign_id":"TEST_ONLY_V686_HTTP"}', encoding="utf-8"
            )

            env = dict(os.environ)
            env.update(
                DATABASE_URL=dsn,
                FIA_FORWARD_OOS_ENABLED="0",
                CLEAR_NASDAQ_AUTH_SECRET=AUTH_SECRET,
                CLEAR_NASDAQ_AUTH_STATE_DIR=str(temp_root / "auth"),
                CLEAR_NASDAQ_AUTH_DB_PATH=str(temp_root / "auth.sqlite3"),
                CLEAR_NASDAQ_AUTH_SECRET_FILE=str(temp_root / "auth_secret"),
                CLEAR_NASDAQ_SCIENTIFIC_OPERATION_SECRET=SCIENCE_SECRET,
            )

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = "http://127.0.0.1:%d" % port
            log_path = output / "v686-app-server.log"

            with log_path.open("w", encoding="utf-8") as logs:
                process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                    cwd=str(backend), env=env, stdout=logs, stderr=subprocess.STDOUT,
                )

                deadline = time.monotonic() + 45
                ready = False
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        status, payload = request_json(base, "/api/health", timeout=1)
                        if status == 200:
                            ready = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.25)
                require(checks, "app_started", ready, {"returncode": process.poll()})
                if not ready:
                    raise RuntimeError("APP_STARTUP_FAILED_OR_TIMEOUT")

                status, health = request_json(base, "/api/health")
                require(checks, "health_200", status == 200 and health.get("ok") is True,
                        {"status": status, "payload": health})

                status, campaign = request_json(base, "/api/forward-oos/campaign")
                require(checks, "campaign_read_public", status == 200, {"status": status})
                require(checks, "campaign_fails_closed",
                        campaign.get("operational_ok") is False
                        and campaign.get("status") != "READY"
                        and campaign.get("metrics_available") is False,
                        campaign)

                status, report_payload = request_json(base, "/api/forward-oos/report")
                require(checks, "report_read_public", status == 200, {"status": status})
                require(checks, "invalid_test_seal_not_scientifically_ok",
                        report_payload.get("ok") is False, report_payload)

                science_header = {"X-Clear-Nasdaq-Scientific-Secret": SCIENCE_SECRET}
                status, payload = request_json(base, "/api/forward-oos/run-once", method="POST", headers=science_header)
                require(checks, "run_once_rejects_anonymous_member",
                        status == 401, {"status": status, "payload": payload})

                status, signup = request_json(
                    base, "/api/auth/signup", method="POST",
                    body={"display_name": "V686 Test", "email": "v686@example.test", "password": "v686Password12345"},
                )
                token = signup.get("token") if isinstance(signup, dict) else None
                require(checks, "signup_real_route", status == 200 and bool(token),
                        {"status": status, "ok": signup.get("ok") if isinstance(signup, dict) else None})
                auth = {"Authorization": "Bearer " + str(token)}

                status, payload = request_json(base, "/api/forward-oos/run-once", method="POST", headers=auth)
                require(checks, "membership_alone_cannot_run_once",
                        status == 403 and payload.get("detail") == "SCIENTIFIC_OPERATION_FORBIDDEN",
                        {"status": status, "payload": payload})

                wrong = {**auth, "X-Clear-Nasdaq-Scientific-Secret": SCIENCE_SECRET + "x"}
                status, payload = request_json(base, "/api/forward-oos/run-once", method="POST", headers=wrong)
                require(checks, "wrong_science_secret_cannot_run_once",
                        status == 403 and payload.get("detail") == "SCIENTIFIC_OPERATION_FORBIDDEN",
                        {"status": status, "payload": payload})

                both = {**auth, "X-Clear-Nasdaq-Scientific-Secret": SCIENCE_SECRET}
                marker = "TEST_V686_HTTP_PROBE"
                status, created = request_json(
                    base, "/api/forward-oos/durability/test-fixture", method="POST",
                    body={"marker": marker}, headers=both,
                )
                require(checks, "two_factor_test_fixture_create",
                        status == 200 and created.get("ok") is True and created.get("is_test") is True,
                        {"status": status, "payload": created})

                status, readback = request_json(base, "/api/forward-oos/durability/test-fixture/" + marker)
                require(checks, "test_fixture_readback",
                        status == 200 and readback.get("found") is True,
                        {"status": status, "payload": readback})

                status, deleted = request_json(
                    base, "/api/forward-oos/durability/test-fixture/" + marker,
                    method="DELETE", headers=both,
                )
                require(checks, "two_factor_test_fixture_delete",
                        status == 200 and deleted.get("deleted") == 1
                        and deleted.get("production_rows_touched") == 0,
                        {"status": status, "payload": deleted})

                with psycopg.connect(dsn) as conn:
                    prod = conn.execute("SELECT COUNT(*) FROM forward_oos_events WHERE is_test=FALSE").fetchone()[0]
                    tests = conn.execute("SELECT COUNT(*) FROM forward_oos_events WHERE is_test=TRUE").fetchone()[0]
                require(checks, "http_test_left_zero_production_rows", prod == 0, {"count": prod})
                require(checks, "http_test_fixture_cleaned_up", tests == 0, {"count": tests})

            report["result"] = "PASS" if checks and all(item["pass"] for item in checks) else "FAIL"
    except Exception as exc:
        report["result"] = "FAIL"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        with psycopg.connect(base_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))

    (output / "v686-http-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
