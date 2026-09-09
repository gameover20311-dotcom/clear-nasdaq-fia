from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"PATCH_ANCHOR_MISSING: {path}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Public manual Forward-OOS trigger must be authenticated.
replace_once(
    "backend/fia/forward_oos_api.py",
    '''    @app.post("/api/forward-oos/run-once")\n    async def forward_oos_run_once():\n        # Manual invocation does NOT bypass the live checkpoint and therefore\n        # cannot create hindsight/backfilled forecasts.\n        return await run_once(hub, build_forecast)\n''',
    '''    @app.post("/api/forward-oos/run-once")\n    async def forward_oos_run_once(\n        authorization: Optional[str] = Header(default=None),\n    ):\n        # Manual invocation is a write-capable operational surface. It does NOT\n        # bypass the live checkpoint, but it can consume provider quota, so it\n        # must never be public/anonymous.\n        from fia.auth_api import _bearer, decode_session_token\n        try:\n            decode_session_token(_bearer(authorization))\n        except Exception as exc:\n            raise HTTPException(status_code=401, detail="AUTH_REQUIRED") from exc\n        return await run_once(hub, build_forecast)\n''',
)

# 2) Scientific writes fail closed when configured durable storage is down.
replace_once(
    "backend/fia/forward_oos_api.py",
    '''        try:\n            resolution = await resolve_due_forecasts(hub, DEFAULT_ROOT)\n''',
    '''        try:\n            from fia.oos_guard import require_durable_before_scientific_write\n            durability = require_durable_before_scientific_write(DEFAULT_ROOT)\n            if not durability.get("append_allowed"):\n                return {\n                    "ok": False,\n                    "skipped": True,\n                    "reason": "DURABILITY_UNAVAILABLE_FAIL_CLOSED",\n                    "durability": durability,\n                    "report": forward_report(DEFAULT_ROOT),\n                }\n            resolution = await resolve_due_forecasts(hub, DEFAULT_ROOT)\n''',
)

# Report durability + configured expiry from one truthful helper.
replace_once(
    "backend/fia/forward_oos_api.py",
    '''        from fia.forward_oos_durable import durability_status\n        led = verify_ledger(DEFAULT_ROOT)\n''',
    '''        from fia.oos_guard import durability_guard_status\n        led = verify_ledger(DEFAULT_ROOT)\n''',
)
replace_once(
    "backend/fia/forward_oos_api.py",
    '''            "durability": durability_status(DEFAULT_ROOT),\n''',
    '''            "durability": durability_guard_status(DEFAULT_ROOT),\n''',
)
replace_once(
    "backend/fia/forward_oos_api.py",
    '''        from fia.forward_oos_durable import durability_status\n        return durability_status(DEFAULT_ROOT)\n''',
    '''        from fia.oos_guard import durability_guard_status\n        return durability_guard_status(DEFAULT_ROOT)\n''',
)

# Include durability on the compact status endpoint too.
replace_once(
    "backend/fia/forward_oos_api.py",
    '''            "report": forward_report(DEFAULT_ROOT),\n        }\n\n    @app.get("/api/forward-oos/report")\n''',
    '''            "report": forward_report(DEFAULT_ROOT),\n            "durability": __import__("fia.oos_guard", fromlist=["durability_guard_status"]).durability_guard_status(DEFAULT_ROOT),\n        }\n\n    @app.get("/api/forward-oos/report")\n''',
)

# FastAPI 0.141 / Starlette 1.x removed Starlette.add_event_handler. FastAPI's
# APIRouter retains the compatibility bridge, so keep the existing worker
# semantics while moving registration to the supported compatibility surface.
replace_once(
    "backend/fia/forward_oos_api.py",
    '''    app.add_event_handler("startup", startup)\n    app.add_event_handler("shutdown", shutdown)\n''',
    '''    app.router.add_event_handler("startup", startup)\n    app.router.add_event_handler("shutdown", shutdown)\n''',
)

# 3) Replace wildcard CORS with an explicit configurable allow-list.
replace_once(
    "backend/main.py",
    '''import csv\nimport json\nfrom pathlib import Path\n''',
    '''import csv\nimport json\nimport os\nfrom pathlib import Path\n''',
)
replace_once(
    "backend/main.py",
    '''app.add_middleware(\n    CORSMiddleware,\n    allow_origins=["*"],\n    allow_methods=["*"],\n    allow_headers=["*"],\n)\n''',
    '''_cors_default = (\n    "https://clear-nasdaq-fia.vercel.app,"\n    "http://localhost:3000,http://127.0.0.1:3000"\n)\n_cors_origins = [\n    origin.strip().rstrip("/")\n    for origin in str(os.getenv("FIA_CORS_ALLOWED_ORIGINS", _cors_default)).split(",")\n    if origin.strip() and origin.strip() != "*"\n]\napp.add_middleware(\n    CORSMiddleware,\n    allow_origins=_cors_origins,\n    allow_credentials=True,\n    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],\n    allow_headers=["Authorization", "Content-Type", "Accept"],\n)\n''',
)

# 4) Freeze-parity regression: make the stale forecast explicitly stale relative
# to the deterministic checkpoint probe. The former fixture inherited a frozen
# generated_at that could become FUTURE relative to the test's separately chosen
# checkpoint, proving the wrong guard. Production validator logic is unchanged.
replace_once(
    "backend/fia/test_freeze_parity_v667.py",
    '''with _Seal():\n    stale_probe = try_lock(premove, tmp, state_probe, fc=base_fc)\ncheck("[3g] a forecast older than the lock window is refused",\n      stale_probe["created"] is False\n      and stale_probe["reason"] == "FORECAST_NOT_FRESH_ENOUGH_TO_LOCK",\n      json.dumps(stale_probe)[:160])\n\nlock_fc = copy.deepcopy(base_fc)\nlock_fc["generated_at"] = state_probe.isoformat()\n''',
    '''stale_fc = copy.deepcopy(base_fc)\nstale_fc["generated_at"] = (state_probe - __import__("datetime").timedelta(minutes=16)).isoformat()\nwith _Seal():\n    stale_probe = try_lock(premove, tmp, state_probe, fc=stale_fc)\ncheck("[3g] a forecast older than the lock window is refused",\n      stale_probe["created"] is False\n      and stale_probe["reason"] == "FORECAST_NOT_FRESH_ENOUGH_TO_LOCK",\n      json.dumps(stale_probe)[:160])\n\nlock_fc = copy.deepcopy(base_fc)\nlock_fc["generated_at"] = state_probe.isoformat()\n''',
)

print("A2Z deterministic source patches applied")
