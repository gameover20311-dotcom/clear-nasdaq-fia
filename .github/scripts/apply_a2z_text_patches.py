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
replace_once(
    "backend/fia/forward_oos_api.py",
    '''            "report": forward_report(DEFAULT_ROOT),\n        }\n\n    @app.get("/api/forward-oos/report")\n''',
    '''            "report": forward_report(DEFAULT_ROOT),\n            "durability": __import__("fia.oos_guard", fromlist=["durability_guard_status"]).durability_guard_status(DEFAULT_ROOT),\n        }\n\n    @app.get("/api/forward-oos/report")\n''',
)
replace_once(
    "backend/fia/forward_oos_api.py",
    '''    app.add_event_handler("startup", startup)\n    app.add_event_handler("shutdown", shutdown)\n''',
    '''    app.router.add_event_handler("startup", startup)\n    app.router.add_event_handler("shutdown", shutdown)\n''',
)

# 3) Explicit CORS allow-list.
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

# 4) Deterministic stale fixture.
replace_once(
    "backend/fia/test_freeze_parity_v667.py",
    '''with _Seal():\n    stale_probe = try_lock(premove, tmp, state_probe, fc=base_fc)\ncheck("[3g] a forecast older than the lock window is refused",\n      stale_probe["created"] is False\n      and stale_probe["reason"] == "FORECAST_NOT_FRESH_ENOUGH_TO_LOCK",\n      json.dumps(stale_probe)[:160])\n\nlock_fc = copy.deepcopy(base_fc)\nlock_fc["generated_at"] = state_probe.isoformat()\n''',
    '''stale_fc = copy.deepcopy(base_fc)\nstale_fc["generated_at"] = (state_probe - __import__("datetime").timedelta(minutes=16)).isoformat()\nwith _Seal():\n    stale_probe = try_lock(premove, tmp, state_probe, fc=stale_fc)\ncheck("[3g] a forecast older than the lock window is refused",\n      stale_probe["created"] is False\n      and stale_probe["reason"] == "FORECAST_NOT_FRESH_ENOUGH_TO_LOCK",\n      json.dumps(stale_probe)[:160])\n\nlock_fc = copy.deepcopy(base_fc)\nlock_fc["generated_at"] = state_probe.isoformat()\n''',
)

# 5) Hardened candidate must not masquerade as the immutable historical seal.
replace_once(
    "backend/fia/test_freeze_parity_v667.py",
    '''_live_seal = forward_oos.verify_campaign_seal()\ncheck("[3d2] the campaign seal is currently VALID (required before freeze)",\n      _live_seal.get("ok") is True\n      and _live_seal.get("model_fingerprint_match") is True,\n      json.dumps({k: _live_seal.get(k) for k in\n                  ("ok", "seal_hash_valid", "model_fingerprint_match")}))\n''',
    '''_live_seal = forward_oos.verify_campaign_seal()\ncheck("[3d2] historical campaign seal hash remains valid",\n      _live_seal.get("seal_hash_valid") is True,\n      json.dumps({k: _live_seal.get(k) for k in\n                  ("ok", "seal_hash_valid", "model_fingerprint_match")}))\ncheck("[3d3] modified candidate does NOT match historical campaign fingerprint",\n      _live_seal.get("model_fingerprint_match") is False,\n      json.dumps({k: _live_seal.get(k) for k in\n                  ("ok", "seal_hash_valid", "model_fingerprint_match")}))\n''',
)

# 6) Abstention test uses a fresh isolated real seal, never copied production history.
replace_once(
    "backend/fia/test_session_abstention_v665.py",
    '''    shutil.copy(F.DEFAULT_ROOT / "FORWARD_OOS_CAMPAIGN_SEAL.json",\n                tmp / "FORWARD_OOS_CAMPAIGN_SEAL.json")\n    _cp = F.checkpoint_state\n''',
    '''    test_seal_path = tmp / "FORWARD_OOS_CAMPAIGN_SEAL.json"\n    test_seal = F.write_campaign_seal(test_seal_path)\n    check("isolated abstention test seal valid", test_seal.get("ok") is True)\n    _seal = F.verify_campaign_seal\n    F.verify_campaign_seal = lambda *a, **k: _seal(test_seal_path)\n    _cp = F.checkpoint_state\n''',
)
replace_once(
    "backend/fia/test_session_abstention_v665.py",
    '''    finally:\n        F.checkpoint_state = _cp\n\n    check("abstention record created", r.get("created") is True, json.dumps(r)[:160])\n''',
    '''    finally:\n        F.checkpoint_state = _cp\n        F.verify_campaign_seal = _seal\n\n    check("abstention record created", r.get("created") is True, json.dumps(r)[:160])\n''',
)

# 7) Legacy integrity suites remain historical. Validate the old seal hash and the
# expected fingerprint mismatch, then run synthetic writes under a fresh isolated
# valid seal. Each file executes in its own process, so no production/global state
# survives the test process.
for _path in (
    "backend/fia_forward_oos/test_forward_oos_integrity.py",
    "backend/fia_forward_oos/V2_PRELIVE_ARCHIVE_20260903_065357/test_forward_oos_integrity.py",
):
    replace_once(
        _path,
        '''    seal = verify_campaign_seal()\n    check("campaign seal valid", seal["ok"] is True and seal["seal_hash_valid"] is True)\n    check("campaign model fingerprint frozen", seal["model_fingerprint_match"] is True)\n    check("historical tuning after seal forbidden", seal["policy"]["historical_tuning_after_seal_allowed"] is False)\n\n    with tempfile.TemporaryDirectory() as td:\n        root = Path(td)\n''',
        '''    seal = verify_campaign_seal()\n    check("historical campaign seal hash valid", seal["seal_hash_valid"] is True)\n    check("hardened candidate does not masquerade as historical fingerprint",\n          seal["model_fingerprint_match"] is False)\n    check("historical tuning after seal forbidden", seal["policy"]["historical_tuning_after_seal_allowed"] is False)\n\n    with tempfile.TemporaryDirectory() as td:\n        root = Path(td)\n        import fia.forward_oos as _foos_mod\n        _test_seal_path = root / "FORWARD_OOS_CAMPAIGN_SEAL.json"\n        _test_seal = _foos_mod.write_campaign_seal(_test_seal_path)\n        check("isolated synthetic test seal valid", _test_seal.get("ok") is True)\n        _orig_verify_campaign_seal = _foos_mod.verify_campaign_seal\n        _foos_mod.verify_campaign_seal = lambda *a, **k: _orig_verify_campaign_seal(_test_seal_path)\n''',
    )

print("A2Z deterministic source patches applied")
