from pathlib import Path


def replace_once(path: str, old: str, new: str) -> bool:
    p = Path(path)
    s = p.read_text()
    if new in s:
        return False
    if old not in s:
        raise SystemExit(f"locator not found in {path}: {old[:100]!r}")
    p.write_text(s.replace(old, new, 1))
    return True


def replace_block(path: str, start: str, end: str | None, new: str) -> bool:
    p = Path(path)
    s = p.read_text()
    if new.strip() in s:
        return False
    a = s.find(start)
    if a < 0:
        raise SystemExit(f"start locator not found in {path}: {start}")
    b = s.find(end, a + len(start)) if end is not None else len(s)
    if b < 0:
        raise SystemExit(f"end locator not found in {path}: {end}")
    p.write_text(s[:a] + new.rstrip() + "\n\n\n" + s[b:])
    return True


def main() -> None:
    auth = Path("backend/fia/auth_api.py")
    s = auth.read_text()
    marker = "def install_auth_routes(app) -> None:"
    helper = '''SCIENTIFIC_OPERATION_ENV = "FIA_SCIENTIFIC_OPERATION_SECRET"
SCIENTIFIC_OPERATION_HEADER = "x-fia-scientific-operation"


def scientific_operation_authorized(request: Any, *, required: bool = True) -> bool:
    """Authorize scientific state mutation with a server-only credential.

    A normal membership/session token is intentionally unrelated to this
    boundary. Optional callers remain read-only when the header is absent.
    Secrets are never returned or logged.
    """
    supplied = str(getattr(request, "headers", {}).get(SCIENTIFIC_OPERATION_HEADER, "") or "").strip()
    configured = str(os.getenv(SCIENTIFIC_OPERATION_ENV) or "").strip()
    if not supplied:
        if required:
            raise HTTPException(status_code=403, detail="SCIENTIFIC_OPERATION_AUTH_REQUIRED")
        return False
    if len(configured) < 32:
        raise HTTPException(status_code=503, detail="SCIENTIFIC_OPERATION_AUTH_NOT_CONFIGURED")
    if not hmac.compare_digest(supplied.encode("utf-8"), configured.encode("utf-8")):
        raise HTTPException(status_code=403, detail="SCIENTIFIC_OPERATION_AUTH_FAILED")
    return True


'''
    if "def scientific_operation_authorized(" not in s:
        if marker not in s:
            raise SystemExit("auth install locator missing")
        auth.write_text(s.replace(marker, helper + marker, 1))

    replace_once(
        "backend/main.py",
        "from fastapi import FastAPI, UploadFile, File, HTTPException, Form",
        "from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request",
    )
    replace_once(
        "backend/main.py",
        "from fia.three_way_confluence import build_three_way_confluence\n",
        "from fia.three_way_confluence import build_three_way_confluence\nfrom fia.auth_api import scientific_operation_authorized\n",
    )

    replace_block(
        "backend/main.py",
        '@app.get("/api/forecast")',
        '@app.get("/api/liquidity")',
        '''@app.get("/api/forecast")
async def forecast(request: Request):
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)
    scientific_write = scientific_operation_authorized(request, required=False)

    if scientific_write:
        try:
            snapshot_payload = snapshot_data.get("data", {})
            nq_price = snapshot_payload.get("nq_futures_price")
            record_fia_forecast(
                fia_forecast,
                entry_price=nq_price,
                output_path="fia_backtest_phase14/data/historical_predictions.csv",
            )
        except Exception as exc:
            print("Prediction recorder ERROR:", type(exc).__name__)
        try:
            phase26_accuracy = build_accuracy_assessment(fia_forecast, snapshot_data)
            record_forward_forecast(fia_forecast, snapshot_data, phase26_accuracy)
            asyncio.create_task(resolve_due_forward_records())
        except Exception as exc:
            print("Phase26 forward recorder ERROR:", type(exc).__name__)
    return fia_forecast''',
    )

    replace_block(
        "backend/main.py",
        '@app.post("/api/confluence")',
        '@app.get("/api/learning/status")',
        '''@app.post("/api/confluence")
async def confluence(request: ConfluenceRequest, http_request: Request):
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)
    accuracy_assessment = build_accuracy_assessment(fia_forecast, snapshot_data)
    assessment = build_confluence_assessment(
        fia_forecast,
        accuracy_assessment,
        request.chart_analysis,
        snapshot_data,
    )
    scientific_write = scientific_operation_authorized(http_request, required=False)
    if scientific_write:
        try:
            rec = record_forward_forecast(fia_forecast, snapshot_data, accuracy_assessment)
            if rec.get("ok") and rec.get("prediction_id"):
                linked = attach_confluence(rec["prediction_id"], assessment, accuracy_assessment)
                assessment["research_alert"] = linked.get("alert") or build_research_alert(accuracy_assessment, assessment)
            else:
                assessment["research_alert"] = build_research_alert(accuracy_assessment, assessment)
            asyncio.create_task(resolve_due_forward_records())
        except Exception as exc:
            assessment["research_alert"] = build_research_alert(accuracy_assessment, assessment)
            assessment["phase26_warning"] = "Forward learning attachment unavailable: %s" % type(exc).__name__
    else:
        assessment["research_alert"] = build_research_alert(accuracy_assessment, assessment)
    return assessment''',
    )

    replace_block(
        "backend/main.py",
        '@app.get("/api/learning/status")',
        '@app.post("/api/analysis/compare")',
        '''@app.get("/api/learning/status")
async def learning_status():
    return build_learning_status()


@app.post("/api/learning/resolve")
async def learning_resolve(request: Request):
    scientific_operation_authorized(request, required=True)
    changed = await resolve_due_forward_records()
    payload = build_learning_status()
    payload["resolved_fields_updated"] = changed
    return payload''',
    )

    replace_block(
        "backend/main.py",
        '@app.get("/api/cognitive/forecast")',
        '@app.get("/api/cognitive/status")',
        '''@app.get("/api/cognitive/forecast")
async def cognitive_forecast(request: Request, deep: bool = False, horizon: str = "8h"):
    horizon = str(horizon or "8h").lower()
    if horizon not in {"4h", "8h"}:
        raise HTTPException(status_code=400, detail="horizon must be 4h or 8h")
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)
    persist = scientific_operation_authorized(request, required=False)
    if deep:
        return await build_deep_cognitive_report(
            hub, snapshot_data, fia_forecast, horizon=horizon, persist=persist
        )
    return build_cognitive_report(
        snapshot_data, fia_forecast, horizon=horizon, persist=persist
    )''',
    )

    replace_once(
        "backend/fia/premove_api.py",
        "from typing import Any\n",
        "from typing import Any\nfrom fastapi import Request\nfrom .auth_api import scientific_operation_authorized\n",
    )
    replace_once(
        "backend/fia/premove_api.py",
        "async def fia_premove():\n            snapshot = await hub.snapshot()\n            forecast = build_forecast(snapshot)\n            return analyze_premove(forecast, snapshot, record=True)",
        "async def fia_premove(request: Request):\n            snapshot = await hub.snapshot()\n            forecast = build_forecast(snapshot)\n            record = scientific_operation_authorized(request, required=False)\n            return analyze_premove(forecast, snapshot, record=record)",
    )

    replace_once(
        "backend/fia/premove_max_api.py",
        "from typing import Any\n",
        "from typing import Any\nfrom fastapi import Request\nfrom .auth_api import scientific_operation_authorized\n",
    )
    replace_once(
        "backend/fia/premove_max_api.py",
        "async def fia_premove_max():\n            snapshot = await hub.snapshot()\n            forecast = build_forecast(snapshot)\n            return analyze_premove_max(forecast, snapshot, record=True)",
        "async def fia_premove_max(request: Request):\n            snapshot = await hub.snapshot()\n            forecast = build_forecast(snapshot)\n            record = scientific_operation_authorized(request, required=False)\n            return analyze_premove_max(forecast, snapshot, record=record)",
    )

    replace_once(
        "backend/fia/phase33_api.py",
        "from typing import Any\n",
        "from typing import Any\nfrom fastapi import Request\nfrom .auth_api import scientific_operation_authorized\n",
    )
    replace_once(
        "backend/fia/phase33_api.py",
        "async def phase33_live():\n            snap=await hub.snapshot(); fc=build_forecast(snap); return analyze_phase33(fc,snap,record=True)",
        "async def phase33_live(request: Request):\n            snap=await hub.snapshot(); fc=build_forecast(snap); record=scientific_operation_authorized(request, required=False); return analyze_phase33(fc,snap,record=record)",
    )

    replace_once(
        "backend/fia/phase34_api.py",
        "from typing import Any\n",
        "from typing import Any\nfrom fastapi import Request\nfrom .auth_api import scientific_operation_authorized\n",
    )
    replace_once(
        "backend/fia/phase34_api.py",
        "async def live():\n            s=await hub.snapshot(); f=build_forecast(s); return analyze_phase34(f,s,True)",
        "async def live(request: Request):\n            s=await hub.snapshot(); f=build_forecast(s); record=scientific_operation_authorized(request, required=False); return analyze_phase34(f,s,record)",
    )

    replace_once(
        "backend/fia/forward_oos_api.py",
        "from fastapi import Body, Header, HTTPException",
        "from fastapi import Body, Header, HTTPException, Request",
    )
    replace_once(
        "backend/fia/forward_oos_api.py",
        "from .forward_oos import (",
        "from .auth_api import scientific_operation_authorized\n\nfrom .forward_oos import (",
    )
    replace_once(
        "backend/fia/forward_oos_api.py",
        "async def forward_oos_durability_fixture(\n        marker: str = Body(..., embed=True),",
        "async def forward_oos_durability_fixture(\n        request: Request,\n        marker: str = Body(..., embed=True),",
    )

    p = Path("backend/fia/forward_oos_api.py")
    s = p.read_text()
    fixture_start = s.index('@app.post("/api/forward-oos/durability/test-fixture")')
    fixture_end = s.index('@app.get("/api/forward-oos/durability/test-fixture/{marker}")', fixture_start)
    block = s[fixture_start:fixture_end]
    if "scientific_operation_authorized(request, required=True)" not in block:
        needle = '        except Exception as exc:\n            raise HTTPException(status_code=401, detail="AUTH_REQUIRED") from exc\n'
        if needle not in block:
            raise SystemExit("fixture auth locator missing")
        block = block.replace(needle, needle + "        scientific_operation_authorized(request, required=True)\n", 1)
        p.write_text(s[:fixture_start] + block + s[fixture_end:])

    replace_once(
        "backend/fia/forward_oos_api.py",
        "async def forward_oos_durability_fixture_delete(\n        marker: str, authorization: Optional[str] = Header(default=None),",
        "async def forward_oos_durability_fixture_delete(\n        marker: str, request: Request, authorization: Optional[str] = Header(default=None),",
    )
    p = Path("backend/fia/forward_oos_api.py")
    s = p.read_text()
    delete_start = s.index('@app.delete("/api/forward-oos/durability/test-fixture/{marker}")')
    run_start = s.index('@app.post("/api/forward-oos/run-once")', delete_start)
    block = s[delete_start:run_start]
    if "scientific_operation_authorized(request, required=True)" not in block:
        needle = '        except Exception as exc:\n            raise HTTPException(status_code=401, detail="AUTH_REQUIRED") from exc\n'
        if needle not in block:
            raise SystemExit("delete auth locator missing")
        block = block.replace(needle, needle + "        scientific_operation_authorized(request, required=True)\n", 1)
        p.write_text(s[:delete_start] + block + s[run_start:])

    replace_once(
        "backend/fia/forward_oos_api.py",
        "async def forward_oos_run_once():\n        # Manual invocation does NOT bypass the live checkpoint",
        "async def forward_oos_run_once(request: Request):\n        scientific_operation_authorized(request, required=True)\n        # Manual invocation does NOT bypass the live checkpoint",
    )

    replace_once(
        "backend/fia_final_cockpit/api.py",
        "from fastapi import Body, HTTPException, Header",
        "from fastapi import Body, HTTPException, Header, Request",
    )
    replace_once(
        "backend/fia_final_cockpit/api.py",
        "from fastapi import Body, HTTPException, Header, Request\n",
        "from fastapi import Body, HTTPException, Header, Request\nfrom fia.auth_api import scientific_operation_authorized\n",
    )
    replace_block(
        "backend/fia_final_cockpit/api.py",
        "    @app.post('/api/final/confluence/three-way')",
        None,
        '''    @app.post('/api/final/confluence/three-way')
    async def final_three_way_confluence(http_request: Request, request: Dict[str,Any]=Body(...)):
        try:
            from fia.accuracy_engine import build_accuracy_assessment
            from fia.confluence_engine import build_confluence_assessment
            from fia.three_way_confluence import build_three_way_confluence
            from fia.learning_engine import record_forward_forecast, attach_confluence, build_research_alert, resolve_due_forward_records
            user_analysis=request.get('user_analysis') if isinstance(request.get('user_analysis'),dict) else {}
            vision_analysis=request.get('vision_analysis') if isinstance(request.get('vision_analysis'),dict) else {}
            snapshot_data=await hub.snapshot(); fia_forecast=build_forecast(snapshot_data); accuracy=build_accuracy_assessment(fia_forecast,snapshot_data)
            phase25=build_confluence_assessment(fia_forecast,accuracy,vision_analysis,snapshot_data)
            result=build_three_way_confluence(fia_forecast,user_analysis,vision_analysis,phase25); result['phase25']=phase25
            scientific_write=scientific_operation_authorized(http_request, required=False)
            if scientific_write:
                try:
                    rec=record_forward_forecast(fia_forecast,snapshot_data,accuracy)
                    if rec.get('ok') and rec.get('prediction_id'):
                        linked=attach_confluence(rec['prediction_id'],phase25,accuracy)
                        phase25['research_alert']=linked.get('alert') or build_research_alert(accuracy,phase25)
                        result['phase26_prediction_id']=rec['prediction_id']; result['phase26_attached']=bool(linked.get('ok'))
                    else:
                        phase25['research_alert']=build_research_alert(accuracy,phase25); result['phase26_attached']=False
                    asyncio.create_task(resolve_due_forward_records())
                except Exception as exc:
                    phase25['research_alert']=build_research_alert(accuracy,phase25); result['phase26_attached']=False; result['phase26_warning']=type(exc).__name__
                _alert=phase25.get('research_alert') or 'NONE'
                _alert_level=str((_alert.get('level') if isinstance(_alert,dict) else _alert) or 'NONE')
                cache={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'setup_grade':phase25.get('setup_grade'),'confluence_score':phase25.get('confluence_score'),'confluence_alignment':phase25.get('confluence_alignment'),'confluence_completeness':phase25.get('confluence_completeness'),'research_alert':_alert,'research_alert_level':_alert_level,'phase26_prediction_id':result.get('phase26_prediction_id'),'phase26_attached':bool(result.get('phase26_attached')),'research_eligible':phase25.get('research_eligible')}
                _atomic_write_json(_phase25_cache_path(root),cache)
                result['dashboard_phase25_persisted']=True
            else:
                phase25['research_alert']=build_research_alert(accuracy,phase25)
                result['phase26_attached']=False
                result['dashboard_phase25_persisted']=False
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500,detail=type(exc).__name__) from exc''',
    )


if __name__ == "__main__":
    main()
