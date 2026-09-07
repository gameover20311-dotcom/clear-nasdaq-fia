"""V6.6.8 auth storage durability contract.

MEASURED, NOT ASSUMED. On 2026-09-07 two accounts were created through the live
public signup flow on https://clear-nasdaq-fia.onrender.com, verified working,
and then a single redeploy was triggered. Both then returned:

    HTTP 401 INVALID_CREDENTIALS

and the issued session token stopped validating. Render's filesystem, including
the home directory holding auth.sqlite3 and auth_secret, does not survive a
deploy. This suite pins the contract that came out of that measurement:

  * the store must report what it actually is
  * it must NEVER claim durability it does not have
  * passwords are hashed in both backends, never stored or echoed
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


def reload_auth(**env):
    for k in ("DATABASE_URL",):
        os.environ.pop(k, None)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import fia.auth_api as a
    return importlib.reload(a)


print("\n[A] THE STORE REPORTS WHAT IT ACTUALLY IS")
a = reload_auth()
d = a.durable_backend()
check("no DATABASE_URL -> sqlite", d["backend"] == "sqlite", str(d))
check("no DATABASE_URL -> EPHEMERAL", d["durability"] == "EPHEMERAL", str(d))
check("no DATABASE_URL -> survives_redeploy False", d["survives_redeploy"] is False)
check("the reason is stated in words", "redeploy" in d["detail"].lower(), d["detail"])

print("\n[B] IT NEVER CLAIMS DURABILITY IT DOES NOT HAVE")
a = reload_auth(DATABASE_URL="postgresql://user@host/db")
d = a.durable_backend()
if a._PG_AVAILABLE:
    check("[B] driver present -> DURABLE is claimed only with a URL",
          d["durability"] == "DURABLE" and d["backend"] == "postgres", str(d))
else:
    check("[B] URL set but driver missing -> still EPHEMERAL",
          d["durability"] == "EPHEMERAL" and d["survives_redeploy"] is False, str(d))
    check("[B] the missing driver is named", "psycopg" in d["detail"], d["detail"])

print("\n[C] PLACEHOLDER TRANSLATION IS SAFE")
q = a._PgConn._q
check("[C1] positional params translate", q("SELECT 1 WHERE a=? AND b=?")
      == "SELECT 1 WHERE a=%s AND b=%s")
check("[C2] a '?' inside a string literal is NOT translated",
      q("SELECT 1 WHERE a=? AND b='what? really'")
      == "SELECT 1 WHERE a=%s AND b='what? really'",
      q("SELECT 1 WHERE a=? AND b='what? really'"))
check("[C3] no params -> unchanged", q("SELECT 1") == "SELECT 1")

print("\n[D] PASSWORDS ARE NEVER STORED IN PLAINTEXT")
a = reload_auth()
src = Path(a.__file__).read_text()
check("[D1] a KDF is used", "scrypt" in src and "pbkdf2" in src)
check("[D2] the users table stores a salt and a hash, not a password",
      "password_salt" in src and "password_hash" in src and "password TEXT" not in src)
salt = b"0123456789abcdef"
h1 = a._hash_password("Correct-Horse-1", salt) if hasattr(a, "_hash_password") else None
if h1 is not None:
    check("[D3] hashing is deterministic for the same salt",
          h1 == a._hash_password("Correct-Horse-1", salt))
    check("[D4] a different password yields a different hash",
          h1 != a._hash_password("Correct-Horse-2", salt))
    check("[D5] the plaintext never appears in the stored hash",
          b"Correct-Horse-1" not in (h1 if isinstance(h1, bytes) else str(h1).encode()))

print("\n[E] THE POSTGRES SCHEMA COVERS EVERYTHING AUTH NEEDS")
ddl = " ".join(a._PG_SCHEMA)
for t in ("users", "sessions", "auth_secret"):
    check("[E] table %s is created" % t, "CREATE TABLE IF NOT EXISTS %s" % t in ddl)
check("[E] the signing secret is durable too, not just the accounts",
      "auth_secret" in ddl and "_durable_secret" in src,
      "a regenerated secret invalidates every live session")
check("[E] email uniqueness is enforced in the durable store",
      "idx_users_email" in ddl and "UNIQUE" in ddl)

print("\n[F] FALLBACK STILL WORKS (no silent hard dependency)")
a = reload_auth()
conn = a._connect()
try:
    conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    check("[F] sqlite fallback connects and queries", True)
finally:
    conn.close()

print("\n[G] NO DSN / PASSWORD CAN ESCAPE THROUGH AN ERROR")
# With Postgres in the path a driver error carries the CONNECTION STRING --
# including the password -- in str(exc). The auth error mapper previously echoed
# any unrecognised exception straight to the client.
SECRET_DSN = "postgresql://fiauser:SuperSecretPw123@dpg-x.oregon-postgres.render.com/fia"
for msg in ('connection failed: FATAL: password authentication failed for "%s"' % SECRET_DSN,
            "could not translate host name in '%s'" % SECRET_DSN,
            "psycopg.OperationalError: %s" % SECRET_DSN):
    h = a._http_error(Exception(msg))
    d = str(h.detail)
    check("[G] driver error is opaque (%s...)" % msg[:26],
          "SuperSecretPw123" not in d and "postgresql://" not in d
          and d == "AUTH_BACKEND_ERROR" and h.status_code == 500, d[:60])
for code, expect in (("EMAIL_ALREADY_REGISTERED", 409), ("INVALID_EMAIL", 401)):
    h = a._http_error(Exception(code))
    check("[G] the curated code %s still reaches the client" % code,
          str(h.detail) == code and h.status_code == expect,
          "%s %s" % (h.status_code, h.detail))
check("[G] the safe-detail pattern rejects free text",
      not a._SAFE_DETAIL_RE.match("connection failed: FATAL")
      and bool(a._SAFE_DETAIL_RE.match("EMAIL_ALREADY_REGISTERED")))

print("\n[H] THE HEALTH PAYLOAD CARRIES NO SECRET")
os.environ["DATABASE_URL"] = "postgresql://u:PLAINTEXT_PW@host/db"
a2 = reload_auth(DATABASE_URL="postgresql://u:PLAINTEXT_PW@host/db")
blob = json.dumps(a2.durable_backend())
check("[H] durable_backend() never contains the DSN or password",
      "PLAINTEXT_PW" not in blob and "postgresql://" not in blob, blob)
os.environ.pop("DATABASE_URL", None)

print("\n" + "=" * 64)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.8 AUTH DURABILITY CONTRACT CHECKS PASSED")
