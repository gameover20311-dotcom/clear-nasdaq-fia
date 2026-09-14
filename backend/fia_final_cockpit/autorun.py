from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict

_STARTED = False


def _emit(marker: str, payload: Dict[str, Any]) -> None:
    try:
        print(marker + " " + json.dumps(payload, sort_keys=True, ensure_ascii=False), flush=True)
    except Exception:
        print(marker, flush=True)


def _wait_for_backend(port: str) -> None:
    url = f"http://127.0.0.1:{port}/api/health"
    last = "not_started"
    for _ in range(90):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as response:
                if int(getattr(response, "status", 0) or 0) == 200:
                    return
        except Exception as exc:  # startup race only
            last = type(exc).__name__ + ": " + str(exc)[:160]
        time.sleep(2)
    raise RuntimeError("BACKEND_NOT_READY: " + last)


def _compact_final(value: Any) -> Dict[str, Any]:
    obj = value if isinstance(value, dict) else {}
    return {
        "direction": obj.get("direction"),
        "bullish_probability": obj.get("bullish_probability"),
        "bearish_probability": obj.get("bearish_probability"),
        "confidence": obj.get("confidence"),
        "regime": obj.get("regime"),
    }


def _run_once() -> None:
    started = time.time()
    try:
        backend_root = Path(__file__).resolve().parents[1]
        brain_root = backend_root / "clear_nasdaq_brain"
        if not (brain_root / "fia_brain" / "orchestrator.py").exists():
            raise RuntimeError("CLOUD_BRAIN_ROOT_MISSING")
        if not (brain_root / "config.json").exists():
            raise RuntimeError("CLOUD_BRAIN_CONFIG_MISSING")

        port = str(os.environ.get("PORT") or "10000").strip()
        _wait_for_backend(port)

        brain_root_s = str(brain_root)
        if brain_root_s not in sys.path:
            sys.path.insert(0, brain_root_s)

        # Hosted runtime only. Never claim the local Ollama digest for Groq.
        os.environ["FIA_BASE_URL"] = f"http://127.0.0.1:{port}"
        os.environ["FIA_INFERENCE_PROVIDER"] = "groq"
        os.environ["FIA_PROVIDER_MODEL"] = "openai/gpt-oss-20b"
        os.environ["GROQ_BASE_URL"] = "https://api.groq.com/openai/v1"
        os.environ["FIA_LOCAL_MODEL_DIGEST"] = ""

        from fia_brain.config import load
        from fia_brain.orchestrator import FIABrain

        cfg = load(str(brain_root / "config.json"))
        brain = FIABrain(cfg)

        health = brain.client.health()
        _emit(
            "GPTOSS_AUTORUN_HEALTH",
            {
                "provider": health.get("provider"),
                "provider_model": health.get("provider_model"),
                "ok": bool(health.get("ok")),
                "model_present": bool(health.get("model_present")),
                "error": health.get("error"),
            },
        )
        if not health.get("ok") or not health.get("model_present"):
            raise RuntimeError("HOSTED_GPTOSS_HEALTH_NOT_READY")

        # Shadow/research runtime proof only. No Forward-OOS or BASE mutation.
        result = brain.analyze(False)
        if not isinstance(result, dict):
            raise RuntimeError("INVALID_BRAIN_RESULT")

        passes = result.get("passes") if isinstance(result.get("passes"), dict) else {}
        final = result.get("final") if isinstance(result.get("final"), dict) else {}
        by_horizon = result.get("final_by_horizon") if isinstance(result.get("final_by_horizon"), dict) else {}
        freeze = (passes or {}).get("three_brain_freeze") if isinstance((passes or {}).get("three_brain_freeze"), dict) else {}
        runtime_events = result.get("runtime_events") if isinstance(result.get("runtime_events"), list) else []
        inference_runtime = result.get("inference_runtime") if isinstance(result.get("inference_runtime"), dict) else {}
        summary = {
            "provider": "groq",
            "provider_model": "openai/gpt-oss-20b",
            "model": result.get("model"),
            "status": result.get("status"),
            "error": result.get("error"),
            "specialists": len((passes or {}).get("specialists") or {}),
            "candidates": len((passes or {}).get("candidates") or []),
            "judges": len((passes or {}).get("judges") or []),
            "final_4h": _compact_final(by_horizon.get("4h")),
            "final_8h": _compact_final(by_horizon.get("8h")),
            "direction": final.get("direction"),
            "bullish_probability": final.get("bullish_probability"),
            "bearish_probability": final.get("bearish_probability"),
            "confidence": final.get("confidence"),
            "snapshot_sha256": result.get("snapshot_sha256"),
            "ledger_sha256": result.get("ledger_sha256"),
            "three_brain_freeze_sha256": freeze.get("freeze_sha256"),
            "result_sha256": result.get("result_sha256"),
            "base_fia_modified": result.get("base_fia_modified"),
            "forward_oos_modified": result.get("forward_oos_modified"),
            "runtime_event_count": len(runtime_events),
            "rate_limit_retries": inference_runtime.get("rate_limit_retries"),
            "request_size_retries": inference_runtime.get("request_size_retries"),
            "elapsed_seconds": round(time.time() - started, 2),
        }
        Path("/tmp/clear_nasdaq_gptoss_autorun.json").write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        _emit("GPTOSS_AUTORUN_RUNTIME_EVENTS", {"events": runtime_events})
        _emit(
            "GPTOSS_AUTORUN_PROVIDER_PROVENANCE",
            {
                "provider": inference_runtime.get("provider"),
                "provider_model": inference_runtime.get("provider_model"),
                "runtime_identity_scope": inference_runtime.get("runtime_identity_scope"),
                "rate_limit_retries": inference_runtime.get("rate_limit_retries"),
                "request_size_retries": inference_runtime.get("request_size_retries"),
                "last_request_id_present": bool(inference_runtime.get("last_request_id")),
                "system_fingerprints": inference_runtime.get("system_fingerprints") or [],
            },
        )
        _emit("GPTOSS_AUTORUN_RESULT", summary)
    except Exception as exc:
        _emit(
            "GPTOSS_AUTORUN_ERROR",
            {
                "type": type(exc).__name__,
                "error": str(exc)[:500],
                "elapsed_seconds": round(time.time() - started, 2),
            },
        )


def start() -> None:
    global _STARTED
    if _STARTED:
        return
    if str(os.environ.get("FIA_AUTO_GPTOSS_ONCE") or "").strip() != "1":
        return
    # Avoid firing during build/test Python processes. The live Render process is uvicorn.
    if "uvicorn" not in " ".join(sys.argv).lower():
        return
    _STARTED = True
    thread = threading.Thread(target=_run_once, name="clear-nasdaq-gptoss-once", daemon=True)
    thread.start()
