from __future__ import annotations

"""CLEAR NASDAQ local membership/authentication API.

Design goals:
- one membership tier: FULL_ACCESS
- no plaintext passwords
- no auth secret shipped in source
- fail closed when the auth secret is not configured
- Python 3.9 compatible
- local SQLite storage with WAL and bounded account lockout
- signed, expiring session token usable by the Next.js access gate

This is an application access layer, not a billing system. Payment/email-verification
providers are deliberately not fabricated.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import Body, Header, HTTPException
from pydantic import BaseModel

AUTH_MARKER = "CLEAR_NASDAQ_OBSIDIAN_FULL_ACCESS_V3_1"
PLAN = "FULL_ACCESS"
SESSION_SECONDS = 7 * 24 * 60 * 60
LOCK_AFTER_FAILURES = 5
LOCK_SECONDS = 10 * 60
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SignupRequest(BaseModel):
    display_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_dir() -> Path:
    configured = str(os.getenv("CLEAR_NASDAQ_AUTH_STATE_DIR") or "").strip()
    path = Path(configured).expanduser() if configured else (Path.home() / ".clear_nasdaq_fia_auth")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_path() -> Path:
    configured = str(os.getenv("CLEAR_NASDAQ_AUTH_DB_PATH") or "").strip()
    return Path(configured).expanduser() if configured else (_state_dir() / "auth.sqlite3")


def _secret_path() -> Path:
    configured = str(os.getenv("CLEAR_NASDAQ_AUTH_SECRET_FILE") or "").strip()
    return Path(configured).expanduser() if configured else (_state_dir() / "auth_secret")


def _auth_secret() -> bytes:
    raw = str(os.getenv("CLEAR_NASDAQ_AUTH_SECRET") or "").strip()
    if not raw:
        path = _secret_path()
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            raw = ""
    if len(raw) < 32:
        raise RuntimeError("CLEAR_NASDAQ_AUTH_SECRET_NOT_CONFIGURED")
    return raw.encode("utf-8")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'FULL_ACCESS',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_login_at INTEGER
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            nonce_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            issued_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    conn.commit()
    return conn


def _normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("INVALID_EMAIL")
    return email


def _normalize_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if len(name) < 2 or len(name) > 64:
        raise ValueError("DISPLAY_NAME_MUST_BE_2_TO_64_CHARACTERS")
    return name


def _validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 10:
        raise ValueError("PASSWORD_MUST_BE_AT_LEAST_10_CHARACTERS")
    if len(password) > 128:
        raise ValueError("PASSWORD_TOO_LONG")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("PASSWORD_MUST_INCLUDE_A_LETTER_AND_A_NUMBER")
    return password


# V6.6.2: scrypt is only present when Python is linked against a real OpenSSL.
# The stock macOS python3.9 is linked against LibreSSL 2.8.3, where
# hashlib.scrypt does not exist -- so create_user() raised AttributeError and
# account signup was broken on this exact machine. Prefer scrypt where it is
# available and fall back to PBKDF2-HMAC-SHA256, which is always present.
_SCRYPT_AVAILABLE = hasattr(hashlib, "scrypt")
_PBKDF2_ITERATIONS = 600_000          # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
_KDF_SCRYPT = "scrypt"
_KDF_PBKDF2 = "pbkdf2_sha256"


def active_kdf() -> str:
    """Which key-derivation function this interpreter will use for NEW passwords."""
    return _KDF_SCRYPT if _SCRYPT_AVAILABLE else _KDF_PBKDF2


def _password_digest(password: str, salt: bytes, kdf: str = None) -> bytes:
    kdf = kdf or active_kdf()
    if kdf == _KDF_SCRYPT:
        if not _SCRYPT_AVAILABLE:
            raise RuntimeError("scrypt hash present but scrypt is unavailable in this interpreter")
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    if kdf == _KDF_PBKDF2:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                   _PBKDF2_ITERATIONS, dklen=32)
    raise ValueError("unknown kdf: %r" % (kdf,))


def _encode_password(password: str) -> Tuple[str, str]:
    salt = secrets.token_bytes(16)
    kdf = active_kdf()
    digest = _password_digest(password, salt, kdf)
    # The salt field carries an explicit KDF tag so stored hashes stay verifiable
    # if the interpreter later gains or loses scrypt. Untagged salts are legacy scrypt.
    salt_text = kdf + "$" + base64.urlsafe_b64encode(salt).decode("ascii")
    return salt_text, base64.urlsafe_b64encode(digest).decode("ascii")


def _decode_salt(salt_text: str) -> Tuple[str, bytes]:
    text = str(salt_text or "")
    if "$" in text:
        kdf, _, raw = text.partition("$")
        return kdf, base64.urlsafe_b64decode(raw.encode("ascii"))
    # Legacy rows were written before the KDF tag existed and are always scrypt.
    return _KDF_SCRYPT, base64.urlsafe_b64decode(text.encode("ascii"))


def _verify_password(password: str, salt_text: str, hash_text: str) -> bool:
    try:
        kdf, salt = _decode_salt(salt_text)
        expected = base64.urlsafe_b64decode(hash_text.encode("ascii"))
        actual = _password_digest(password, salt, kdf)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _public_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "display_name": str(row["display_name"]),
        "email": str(row["email"]),
        "plan": str(row["plan"]),
        "status": str(row["status"]),
        "created_at": int(row["created_at"]),
    }


def create_user(display_name: str, email: str, password: str) -> Dict[str, Any]:
    name = _normalize_name(display_name)
    normalized_email = _normalize_email(email)
    clean_password = _validate_password(password)
    salt_text, hash_text = _encode_password(clean_password)
    now = int(time.time())
    user_id = secrets.token_hex(16)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO users (id,display_name,email,password_salt,password_hash,plan,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, name, normalized_email, salt_text, hash_text, PLAN, "ACTIVE", now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise RuntimeError("USER_CREATE_READBACK_FAILED")
        return _public_user(row)
    except sqlite3.IntegrityError as exc:
        raise ValueError("EMAIL_ALREADY_REGISTERED") from exc
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    try:
        normalized_email = _normalize_email(email)
    except ValueError as exc:
        raise ValueError("INVALID_CREDENTIALS") from exc
    supplied = str(password or "")
    now = int(time.time())
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (normalized_email,)).fetchone()
        if row is None:
            # Deliberately perform comparable password work to reduce account enumeration timing signal.
            _password_digest(supplied, b"0" * 16)
            raise ValueError("INVALID_CREDENTIALS")
        if str(row["status"]).upper() != "ACTIVE":
            raise ValueError("ACCOUNT_NOT_ACTIVE")
        locked_until = int(row["locked_until"] or 0)
        if locked_until > now:
            raise ValueError("ACCOUNT_TEMPORARILY_LOCKED")
        valid = _verify_password(supplied, str(row["password_salt"]), str(row["password_hash"]))
        if not valid:
            failures = int(row["failed_attempts"] or 0) + 1
            next_lock = now + LOCK_SECONDS if failures >= LOCK_AFTER_FAILURES else 0
            if next_lock:
                failures = 0
            conn.execute(
                "UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?",
                (failures, next_lock, str(row["id"])),
            )
            conn.commit()
            raise ValueError("INVALID_CREDENTIALS")
        conn.execute(
            "UPDATE users SET failed_attempts=0, locked_until=0, last_login_at=? WHERE id=?",
            (now, str(row["id"])),
        )
        conn.commit()
        fresh = conn.execute("SELECT * FROM users WHERE id=?", (str(row["id"]),)).fetchone()
        if fresh is None:
            raise RuntimeError("USER_READBACK_FAILED")
        return _public_user(fresh)
    finally:
        conn.close()


def _nonce_hash(nonce: str) -> str:
    return hashlib.sha256(str(nonce).encode("utf-8")).hexdigest()


def issue_session_token(user: Dict[str, Any], now: Optional[int] = None) -> str:
    issued = int(now if now is not None else time.time())
    nonce = secrets.token_hex(16)
    payload = {
        "v": 1,
        "sub": str(user["id"]),
        "email": str(user["email"]),
        "plan": PLAN,
        "iat": issued,
        "exp": issued + SESSION_SECONDS,
        "nonce": nonce,
    }
    payload_raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encoded = _b64url(payload_raw)
    signature = hmac.new(_auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    conn = _connect()
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (issued,))
        conn.execute(
            "INSERT INTO sessions (nonce_hash,user_id,issued_at,expires_at,revoked_at) VALUES (?,?,?,?,0)",
            (_nonce_hash(nonce), str(user["id"]), issued, issued + SESSION_SECONDS),
        )
        conn.commit()
    finally:
        conn.close()
    return encoded + "." + _b64url(signature)


def decode_session_token(token: str, now: Optional[int] = None) -> Dict[str, Any]:
    try:
        encoded, signature_text = str(token or "").split(".", 1)
        supplied = _b64url_decode(signature_text)
        expected = hmac.new(_auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("INVALID_SESSION_SIGNATURE")
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        if not isinstance(payload, dict) or int(payload.get("v") or 0) != 1:
            raise ValueError("INVALID_SESSION_PAYLOAD")
        current = int(now if now is not None else time.time())
        if int(payload.get("exp") or 0) <= current:
            raise ValueError("SESSION_EXPIRED")
        if str(payload.get("plan") or "") != PLAN:
            raise ValueError("INVALID_SESSION_PLAN")
        user_id = str(payload.get("sub") or "")
        nonce = str(payload.get("nonce") or "")
        if not user_id or not nonce:
            raise ValueError("INVALID_SESSION_USER")
        conn = _connect()
        try:
            session_row = conn.execute(
                "SELECT * FROM sessions WHERE nonce_hash=? AND user_id=?",
                (_nonce_hash(nonce), user_id),
            ).fetchone()
            if session_row is None:
                raise ValueError("SESSION_NOT_REGISTERED")
            if int(session_row["revoked_at"] or 0) > 0:
                raise ValueError("SESSION_REVOKED")
            if int(session_row["expires_at"] or 0) <= current:
                raise ValueError("SESSION_EXPIRED")
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None or str(row["status"]).upper() != "ACTIVE":
                raise ValueError("SESSION_USER_NOT_ACTIVE")
            user = _public_user(row)
        finally:
            conn.close()
        if user["email"] != str(payload.get("email") or "") or user["plan"] != PLAN:
            raise ValueError("SESSION_IDENTITY_MISMATCH")
        return {"payload": payload, "user": user}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("INVALID_SESSION") from exc



def revoke_session_token(token: str, now: Optional[int] = None) -> None:
    decoded = decode_session_token(token, now=now)
    nonce = str(decoded["payload"].get("nonce") or "")
    if not nonce:
        raise ValueError("INVALID_SESSION")
    current = int(now if now is not None else time.time())
    conn = _connect()
    try:
        conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE nonce_hash=? AND user_id=?",
            (current, _nonce_hash(nonce), str(decoded["user"]["id"])),
        )
        conn.commit()
    finally:
        conn.close()

def _bearer(authorization: Optional[str]) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise ValueError("MISSING_SESSION")
    token = raw[7:].strip()
    if not token:
        raise ValueError("MISSING_SESSION")
    return token


def _http_error(exc: Exception, *, login: bool = False) -> HTTPException:
    code = str(exc)
    if code == "EMAIL_ALREADY_REGISTERED":
        return HTTPException(status_code=409, detail=code)
    if code == "ACCOUNT_TEMPORARILY_LOCKED":
        return HTTPException(status_code=429, detail=code)
    if code.startswith("CLEAR_NASDAQ_AUTH_SECRET"):
        return HTTPException(status_code=503, detail=code)
    if login or code.startswith("INVALID_") or code in {"MISSING_SESSION", "SESSION_EXPIRED", "SESSION_REVOKED", "SESSION_NOT_REGISTERED", "SESSION_USER_NOT_ACTIVE", "SESSION_IDENTITY_MISMATCH"}:
        return HTTPException(status_code=401, detail="INVALID_CREDENTIALS" if login else code)
    return HTTPException(status_code=400, detail=code)


def install_auth_routes(app) -> None:
    @app.get("/api/auth/health")
    async def auth_health():
        try:
            _auth_secret()
            conn = _connect()
            try:
                row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
                users = int(row["n"] if row else 0)
            finally:
                conn.close()
            return {"ok": True, "status": "READY", "plan": PLAN, "users": users, "billing": "NOT_CONFIGURED"}
        except Exception as exc:
            raise _http_error(exc)

    @app.post("/api/auth/signup")
    async def signup(request: SignupRequest = Body(...)):
        try:
            user = create_user(request.display_name, request.email, request.password)
            token = issue_session_token(user)
            return {"ok": True, "token": token, "expires_in": SESSION_SECONDS, "user": user}
        except Exception as exc:
            raise _http_error(exc)

    @app.post("/api/auth/login")
    async def login(request: LoginRequest = Body(...)):
        try:
            user = authenticate_user(request.email, request.password)
            token = issue_session_token(user)
            return {"ok": True, "token": token, "expires_in": SESSION_SECONDS, "user": user}
        except Exception as exc:
            raise _http_error(exc, login=True)

    @app.get("/api/auth/session")
    async def session(authorization: Optional[str] = Header(default=None)):
        try:
            decoded = decode_session_token(_bearer(authorization))
            return {"ok": True, "user": decoded["user"], "expires_at": decoded["payload"]["exp"]}
        except Exception as exc:
            raise _http_error(exc)

    @app.post("/api/auth/logout")
    async def logout(authorization: Optional[str] = Header(default=None)):
        try:
            revoke_session_token(_bearer(authorization))
            return {"ok": True}
        except Exception as exc:
            raise _http_error(exc)
