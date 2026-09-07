from __future__ import annotations
import copy, json, os, re
from pathlib import Path
from typing import Any, Dict, Optional
from .network import assert_loopback_url

DEFAULTS = {
    "fia_base_url": "http://127.0.0.1:8001",
    "ollama_base_url": "http://127.0.0.1:11434",
    "inference_provider": "ollama",
    "groq_base_url": "https://api.groq.com/openai/v1",
    "provider_model": "openai/gpt-oss-20b",
    "model": "gpt-oss:20b",
    # V6.6.2: optional exact-weights pin. The model NAME alone is spoofable
    # (`ollama cp <anything> gpt-oss:20b`), so a digest pin is the only real
    # identity guarantee. Empty string = name-only identity (declared, not silent).
    "model_digest_sha256": "",
    "mode": "max",
    "reasoning_effort": "high",
    "timeout_seconds": 420,
    "http_timeout_seconds": 10,
    "num_ctx": 24576,
    "max_evidence_records": 360,
    "max_evidence_chars": 64000,
    "max_fact_cards": 96,
    "num_predict": 8192,
    "specialist_max_records": 72,
    "specialist_timeout_seconds": 300,
    "core_timeout_seconds": 480,
    "atomic_evidence_endpoint": "/api/dashboard",
    "health_endpoints": ["/api/provider/health"],
    "atomic_max_age_seconds": 180,
    "future_clock_skew_seconds": 30,
    "degraded_confidence_cap": 45,
    "scenario_entropy_gate": True,
    "market_twin_gate": True,
    "novelty_gate": True,
    "failure_memory_gate": True,
}


# V6.6.2 OUTPUT-BUDGET CALIBRATION (measured on Apple M4 / 16 GB unified memory).
#
# gpt-oss:20b emits hidden `thinking` tokens that are charged against num_predict but
# never appear in message.content. The V6.6.1 budgets were therefore not merely tight,
# they made some stages UNCOMPLETABLE: a real end-to-end run on this hardware failed
# with done_reason=length and content_chars=0 on SPECIALIST_CATALYST_FRESHNESS
# (num_predict=1536) and then aborted the whole pipeline on CAUSAL_GRAPH, which
# exhausted the budget at BOTH 3072 (effort=high, 314.6s) and 4096 (effort=medium,
# 464.2s) and produced zero content each time.
#
# Isolated probe of the same CAUSAL_GRAPH stage:
#     num_predict=3072  effort=high    -> FAIL (done_reason=length, 0 chars)
#     num_predict=4096  effort=medium  -> FAIL (done_reason=length, 0 chars)
#     num_predict=8192  effort=medium  -> OK in 194.8s
#
# The budgets below are raised so each stage can actually emit its schema. Reasoning
# effort and context are UNCHANGED, so reasoning quality is not traded away, and the
# fast/balanced/max separation is preserved. 8192 is the validator ceiling.
MODE_POLICIES = {
    "fast": {
        "specialists":{"effort":"low","num_ctx":8192,"num_predict":2048,"max_records":36},
        "core":{"effort":"medium","num_ctx":12288,"num_predict":4096},
        "critics":{"effort":"low","num_ctx":8192,"num_predict":2048},
        "forecast":{"effort":"medium","num_ctx":12288,"num_predict":4096},
    },
    "balanced": {
        "specialists":{"effort":"medium","num_ctx":12288,"num_predict":3072,"max_records":54},
        "core":{"effort":"high","num_ctx":16384,"num_predict":6144},
        "critics":{"effort":"medium","num_ctx":12288,"num_predict":3072},
        "forecast":{"effort":"high","num_ctx":16384,"num_predict":6144},
    },
    # MEASURED on Apple M4 / 16 GB across two full runs and an isolated stage probe:
    # reasoning_effort="high" NEVER completed a core/forecast stage (0 successes in 9
    # attempts). It exhausted the output budget with content_chars=0 or hit the wall
    # clock, costing 770-900s each time before the retry ladder rescued it at "medium",
    # which then succeeded essentially every time. On this hardware "high" is not more
    # reasoning, it is no output. The first attempt therefore starts at "medium".
    # Mode separation is preserved through context and evidence budget
    # (ctx 12288 / 16384 / 24576, specialist max_records 36 / 54 / 72).
    "max": {
        "specialists":{"effort":"medium","num_ctx":16384,"num_predict":4096,"max_records":72},
        "core":{"effort":"medium","num_ctx":24576,"num_predict":8192},
        "critics":{"effort":"medium","num_ctx":16384,"num_predict":4096},
        "forecast":{"effort":"medium","num_ctx":24576,"num_predict":8192},
    },
}

def runtime_policy(cfg: Dict[str,Any]) -> Dict[str,Any]:
    mode=str(cfg.get("mode","max")).lower()
    if mode not in MODE_POLICIES: raise ValueError("invalid mode")
    base=copy.deepcopy(MODE_POLICIES[mode])
    configured_records=int(cfg.get("specialist_max_records",72))
    if mode=="fast": base["specialists"]["max_records"]=min(configured_records,36)
    elif mode=="balanced": base["specialists"]["max_records"]=min(configured_records,54)
    else: base["specialists"]["max_records"]=configured_records
    base["specialists"]["timeout_seconds"]=int(cfg.get("specialist_timeout_seconds",300))
    base["critics"]["timeout_seconds"]=int(cfg.get("specialist_timeout_seconds",300))
    base["core"]["timeout_seconds"]=int(cfg.get("core_timeout_seconds",480))
    base["forecast"]["timeout_seconds"]=int(cfg.get("core_timeout_seconds",480))
    base["mode"]=mode
    return base

def _strict_json(path: Path) -> Dict[str, Any]:
    def bad(x): raise ValueError("non-finite JSON constant forbidden: "+x)
    obj=json.loads(path.read_text(encoding="utf-8"), parse_constant=bad)
    if not isinstance(obj,dict): raise ValueError("config must be a JSON object")
    return obj

def _safe_endpoint(e: Any) -> str:
    if not isinstance(e,str) or not e.startswith("/api/") or ".." in e or "?" in e or "#" in e:
        raise ValueError("unsafe endpoint: "+repr(e))
    return e

def validate(cfg: Dict[str,Any]) -> Dict[str,Any]:
    out=copy.deepcopy(DEFAULTS)
    out.update(copy.deepcopy(cfg))
    assert_loopback_url(str(out["fia_base_url"]))
    provider=str(out.get("inference_provider") or "ollama").strip().lower()
    if provider not in {"ollama","groq"}:
        raise ValueError("invalid inference_provider")
    out["inference_provider"]=provider
    if provider=="ollama":
        assert_loopback_url(str(out["ollama_base_url"]))
    else:
        out["groq_base_url"]=str(out.get("groq_base_url") or "").rstrip("/")
        if out["groq_base_url"]!="https://api.groq.com/openai/v1":
            raise ValueError("Groq endpoint must remain pinned to official api.groq.com")
        if str(out.get("provider_model"))!="openai/gpt-oss-20b":
            raise ValueError("Groq provider model must be openai/gpt-oss-20b")
    if str(out.get("model"))!="gpt-oss:20b":
        raise ValueError("V6 release is pinned to model gpt-oss:20b")
    _dg=str(out.get("model_digest_sha256") or "").strip().lower()
    if _dg and not re.fullmatch(r"[0-9a-f]{64}",_dg):
        raise ValueError("model_digest_sha256 must be 64 lowercase hex chars or empty")
    if provider=="groq" and _dg:
        raise ValueError("local Ollama digest pin cannot be claimed for hosted Groq runtime")
    out["model_digest_sha256"]=_dg
    if str(out.get("mode")) not in {"max","balanced","fast"}:
        raise ValueError("invalid mode")
    if str(out.get("reasoning_effort")) not in {"low","medium","high"}:
        raise ValueError("invalid reasoning_effort")
    for k,lo,hi in (
        ("timeout_seconds",10,900),("http_timeout_seconds",1,30),
        ("num_ctx",4096,131072),("num_predict",256,8192),("specialist_max_records",20,200),("specialist_timeout_seconds",30,900),("core_timeout_seconds",60,900),("max_evidence_records",20,1200),
        ("max_evidence_chars",4000,250000),("max_fact_cards",20,600),
        ("atomic_max_age_seconds",15,1800),("future_clock_skew_seconds",0,300),
        ("degraded_confidence_cap",0,70),
    ):
        v=int(out[k])
        if not lo<=v<=hi: raise ValueError(k+" outside safe range")
        out[k]=v
    out["atomic_evidence_endpoint"]=_safe_endpoint(out["atomic_evidence_endpoint"])
    hs=out.get("health_endpoints")
    if not isinstance(hs,list) or len(hs)!=len(set(map(str,hs))):
        raise ValueError("health_endpoints must be a unique list")
    out["health_endpoints"]=[_safe_endpoint(x) for x in hs]
    if out["atomic_evidence_endpoint"] in out["health_endpoints"]:
        raise ValueError("atomic evidence endpoint must not be duplicated as health endpoint")
    return out

def load(path: Optional[str]=None) -> Dict[str,Any]:
    cfg=copy.deepcopy(DEFAULTS)
    if path:
        p=Path(path)
        if p.exists():
            raw=_strict_json(p)
            unknown=set(raw)-set(DEFAULTS)-{"shadow_ledger","calibration_profile","regime_profile","failure_memory_ledger"}
            if unknown: raise ValueError("unknown config keys: "+", ".join(sorted(unknown)))
            cfg.update(raw)
    cfg["fia_base_url"]=os.getenv("FIA_BASE_URL",cfg["fia_base_url"])
    cfg["ollama_base_url"]=os.getenv("OLLAMA_BASE_URL",cfg["ollama_base_url"])
    cfg["inference_provider"]=os.getenv("FIA_INFERENCE_PROVIDER",cfg["inference_provider"])
    cfg["groq_base_url"]=os.getenv("GROQ_BASE_URL",cfg["groq_base_url"])
    cfg["provider_model"]=os.getenv("FIA_PROVIDER_MODEL",cfg["provider_model"])
    cfg["model"]=os.getenv("FIA_LOCAL_MODEL",cfg["model"])
    cfg["model_digest_sha256"]=os.getenv("FIA_LOCAL_MODEL_DIGEST",cfg.get("model_digest_sha256","") or "")
    base=Path(__file__).resolve().parents[1]
    cfg["shadow_ledger"]=os.getenv("FIA_SHADOW_LEDGER",str(base/"data"/"shadow"/"brain_v6.jsonl"))
    cfg["calibration_profile"]=str(cfg.get("calibration_profile") or (base/"benchmarks"/"calibration_profile.json"))
    cfg["regime_profile"]=str(cfg.get("regime_profile") or (base/"benchmarks"/"regime_profile.json"))
    cfg["failure_memory_ledger"]=str(cfg.get("failure_memory_ledger") or (base/"data"/"memory"/"failure_memory.jsonl"))
    return validate(cfg)
