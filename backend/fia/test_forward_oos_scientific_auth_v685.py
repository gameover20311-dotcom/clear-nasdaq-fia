"""V6.8.5 — independent scientific-operation authorization regression.

Normal product membership is not authority to mutate the prospective scientific
record.  HTTP mutation commands must require BOTH a valid application session
and a separately configured high-entropy operation secret.  Read-only status
routes are intentionally unaffected.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import auth_api, forward_oos_api as api  # noqa: E402

FAILURES = []
ENV = "CLEAR_NASDAQ_SCIENTIFIC_OPERATION_SECRET"
GOOD = "science-operation-secret-0123456789-abcdef"


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


def expect_http(name, status, detail, fn):
    try:
        fn()
    except HTTPException as exc:
        check(name, exc.status_code == status and exc.detail == detail,
              "got=%s:%s" % (exc.status_code, exc.detail))
    else:
        check(name, False, "no HTTPException")


old_env = os.environ.get(ENV)
try:
    print("\n[A] SECRET CONFIGURATION FAILS CLOSED")
    os.environ.pop(ENV, None)
    expect_http("[A1] absent secret -> 503", 503,
                "SCIENTIFIC_OPERATION_SECRET_NOT_CONFIGURED",
                lambda: api._require_scientific_operation_secret(GOOD))

    os.environ[ENV] = "too-short"
    expect_http("[A2] short secret -> 503", 503,
                "SCIENTIFIC_OPERATION_SECRET_NOT_CONFIGURED",
                lambda: api._require_scientific_operation_secret("too-short"))

    print("\n[B] WRONG/MISSING CALLER SECRET IS FORBIDDEN")
    os.environ[ENV] = GOOD
    expect_http("[B1] missing header -> 403", 403,
                "SCIENTIFIC_OPERATION_FORBIDDEN",
                lambda: api._require_scientific_operation_secret(None))
    expect_http("[B2] wrong header -> 403", 403,
                "SCIENTIFIC_OPERATION_FORBIDDEN",
                lambda: api._require_scientific_operation_secret(GOOD + "x"))
    try:
        api._require_scientific_operation_secret(GOOD)
        correct_ok = True
    except Exception:
        correct_ok = False
    check("[B3] exact secret is accepted", correct_ok)

    print("\n[C] MEMBERSHIP AND SCIENTIFIC SECRET ARE BOTH REQUIRED")
    calls = []
    real_require = auth_api.require_authenticated_session
    try:
        auth_api.require_authenticated_session = lambda authorization: calls.append(authorization) or {"user": "fixture"}
        api._authorize_scientific_mutation("Bearer fixture-session", GOOD)
        check("[C1] membership verifier is invoked", calls == ["Bearer fixture-session"], str(calls))

        calls.clear()
        expect_http("[C2] valid membership but wrong operation secret is forbidden", 403,
                    "SCIENTIFIC_OPERATION_FORBIDDEN",
                    lambda: api._authorize_scientific_mutation("Bearer fixture-session", "wrong"))
        check("[C3] membership check still ran before secret rejection",
              calls == ["Bearer fixture-session"], str(calls))

        def deny(_authorization):
            raise HTTPException(status_code=401, detail="MISSING_SESSION")

        auth_api.require_authenticated_session = deny
        expect_http("[C4] operation secret cannot bypass missing membership", 401,
                    "MISSING_SESSION",
                    lambda: api._authorize_scientific_mutation(None, GOOD))
    finally:
        auth_api.require_authenticated_session = real_require

    print("\n[D] EVERY HTTP OOS MUTATION ROUTE USES THE TWO-FACTOR BOUNDARY")
    route_src = inspect.getsource(api.install_forward_oos_routes)
    check("[D1] three mutation handlers call shared scientific authorization",
          route_src.count("_authorize_scientific_mutation(") == 3,
          "count=%d" % route_src.count("_authorize_scientific_mutation("))
    check("[D2] all three accept the independent secret header",
          route_src.count('alias="X-Clear-Nasdaq-Scientific-Secret"') == 3,
          "count=%d" % route_src.count('alias="X-Clear-Nasdaq-Scientific-Secret"'))
    check("[D3] manual run-once remains POST", '@app.post("/api/forward-oos/run-once")' in route_src)
    check("[D4] durability fixture create remains POST",
          '@app.post("/api/forward-oos/durability/test-fixture")' in route_src)
    check("[D5] durability fixture delete remains DELETE",
          '@app.delete("/api/forward-oos/durability/test-fixture/{marker}")' in route_src)
    check("[D6] read-only report remains GET", '@app.get("/api/forward-oos/report")' in route_src)
    check("[D7] read-only verify remains GET", '@app.get("/api/forward-oos/verify")' in route_src)

    print("\n[E] SECRET IS NOT ECHOED OR LOGGED")
    secret_src = inspect.getsource(api._require_scientific_operation_secret)
    check("[E1] comparison is constant-time", "hmac.compare_digest" in secret_src)
    check("[E2] raw expected secret is never put in an exception detail",
          "detail=expected" not in secret_src and "detail=supplied" not in secret_src)
    check("[E3] helper does not print either secret", "print(" not in secret_src)
finally:
    if old_env is None:
        os.environ.pop(ENV, None)
    else:
        os.environ[ENV] = old_env

print("\n" + "=" * 72)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for failure in FAILURES:
        print("   -", failure)
    raise SystemExit(1)
print("FORWARD-OOS SCIENTIFIC OPERATION AUTH: PASS")
