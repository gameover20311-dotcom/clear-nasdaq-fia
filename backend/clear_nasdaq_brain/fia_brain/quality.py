from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import math, re

BAD_ATOMIC_STATUSES={"ERROR","DOWN","FAILED","FAIL","STALE","MISSING","DEAD","UNAVAILABLE"}
# Statuses the backend uses to say "this is not real market data". Treated as
# hard fail-closed reasons: a shadow forecast must never be built on demo output.
NOT_LIVE_ATOMIC_STATUSES={"DEMO","SIMULATED","SIMULATION","SAMPLE","PLACEHOLDER","MOCK","FAKE","SYNTHETIC"}
DEGRADED_ATOMIC_STATUSES={"DEGRADED","PARTIAL"}
PROVIDER_BAD={"ERROR","DOWN","FAILED","FAIL","DEAD","UNHEALTHY","UNAVAILABLE"}
PROVIDER_DEGRADED={"DEGRADED","STALE","PARTIAL"}

_STATUS_SPLIT_RE=re.compile(r"[^A-Z0-9]+")

def status_tokens(status: Any) -> set:
    """Split a status into upper-case tokens.

    The backend emits provider-prefixed compound statuses such as FINNHUB_ERROR.
    Exact-equality membership silently treats those as healthy, so every status
    comparison in this module is token-based instead.
    """
    return {t for t in _STATUS_SPLIT_RE.split(str(status or "").upper()) if t}

def classify_atomic_status(status: Any) -> str:
    """BAD | NOT_LIVE | DEGRADED | OK"""
    toks=status_tokens(status)
    if not toks: return "OK"
    if toks & BAD_ATOMIC_STATUSES: return "BAD"
    if toks & NOT_LIVE_ATOMIC_STATUSES: return "NOT_LIVE"
    if toks & DEGRADED_ATOMIC_STATUSES: return "DEGRADED"
    return "OK"

def classify_provider_status(status: Any) -> str:
    """BAD | DEGRADED | OK | UNKNOWN"""
    toks=status_tokens(status)
    if not toks: return "UNKNOWN"
    if toks & PROVIDER_BAD: return "BAD"
    if toks & PROVIDER_DEGRADED: return "DEGRADED"
    return "OK"

def _parse_dt(x: Any) -> Optional[datetime]:
    if not isinstance(x,str) or not x.strip(): return None
    s=x.strip()
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    try:
        d=datetime.fromisoformat(s)
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None

def _get(d: Any,*path):
    cur=d
    for k in path:
        if not isinstance(cur,dict): return None
        cur=cur.get(k)
    return cur

def _finite_score(x: Any) -> Optional[float]:
    try:
        v=float(x)
        if not math.isfinite(v): return None
        return max(0.0,min(100.0,v))
    except Exception:
        return None

def _provider_summary(payload: Dict[str,Any]) -> Dict[str,Any]:
    """
    Supports both historical flat health schema and the real CLEAR NASDAQ
    v2.1 schema where summary fields live under payload["provider_health"].
    """
    nested=payload.get("provider_health")
    if isinstance(nested,dict):
        return nested
    return payload

def assess(snapshot: Dict[str,Any],cfg: Dict[str,Any]) -> Dict[str,Any]:
    reasons=[]; warnings=[]; cap=100.0
    atomic=str(snapshot.get("atomic_evidence_endpoint") or cfg.get("atomic_evidence_endpoint") or "")
    health=snapshot.get("endpoint_health") or {}
    ah=health.get(atomic) or {}
    if not ah.get("ok"): reasons.append("atomic_evidence_endpoint_unavailable:"+atomic)

    body=(snapshot.get("payloads") or {}).get(atomic)
    if not isinstance(body,dict):
        reasons.append("atomic_dashboard_payload_missing")
        body={}
    if body.get("ok") is False:
        reasons.append("atomic_dashboard_ok_false")

    generated=_parse_dt(body.get("generated_at"))
    age=None
    if generated is None:
        reasons.append("atomic_dashboard_generated_at_missing_or_invalid")
    else:
        age=(datetime.now(timezone.utc)-generated).total_seconds()
        if age < -float(cfg.get("future_clock_skew_seconds",30)):
            reasons.append("atomic_dashboard_timestamp_in_future")
        if age > float(cfg.get("atomic_max_age_seconds",180)):
            reasons.append("atomic_dashboard_too_old")

    # V662: the envelope timestamp is stamped at response-build time, so it ages the
    # RESPONSE, not the DATA. When the backend also publishes the underlying market
    # observation time, age that instead — otherwise the freshness gate is inert.
    data_as_of=_parse_dt(body.get("data_as_of") or _get(body,"live","data_as_of"))
    data_age=None
    if data_as_of is not None:
        data_age=(datetime.now(timezone.utc)-data_as_of).total_seconds()
        if data_age < -float(cfg.get("future_clock_skew_seconds",30)):
            reasons.append("atomic_market_observation_timestamp_in_future")
        if data_age > float(cfg.get("atomic_max_age_seconds",180)):
            reasons.append("atomic_market_observation_too_old")
    else:
        warnings.append("atomic_data_as_of_absent__freshness_gate_uses_response_envelope_only")

    snap_status=str(_get(body,"live","snapshot","status") or "").upper()
    fc_status=str(_get(body,"live","forecast","status") or "").upper()
    for name,status in (("snapshot",snap_status),("forecast",fc_status)):
        verdict=classify_atomic_status(status)
        if verdict=="BAD":
            reasons.append("atomic_"+name+"_status_"+status.lower())
        elif verdict=="NOT_LIVE":
            reasons.append("atomic_"+name+"_not_live_"+status.lower())
        elif verdict=="DEGRADED":
            warnings.append("atomic_"+name+"_degraded")
            cap=min(cap,float(cfg.get("degraded_confidence_cap",45)))

    provider_score=None
    missing_sources=[]
    for ep,payload in (snapshot.get("health_payloads") or {}).items():
        eh=health.get(ep) or {}
        if not eh.get("ok"):
            reasons.append("health_endpoint_unavailable:"+ep)
            continue
        if not isinstance(payload,dict):
            reasons.append("health_payload_invalid:"+ep)
            continue

        summary=_provider_summary(payload)
        # V662: an EMPTY provider-health object is not "schema unknown", it is
        # "no provider reported healthy". Under the project's own
        # unknown-is-not-neutral rule that must fail closed, not merely cap.
        if isinstance(summary,dict) and not summary:
            reasons.append("provider_health_empty_no_provider_reported:"+ep)
            continue
        overall=str(summary.get("overall") or summary.get("status") or "").upper()
        critical=summary.get("critical_missing")
        if isinstance(critical,list) and critical:
            reasons.append("critical_provider_missing:"+",".join(map(str,critical[:8])))

        score=_finite_score(summary.get("score"))
        if score is not None:
            provider_score=score if provider_score is None else min(provider_score,score)
            # Source quality may cap confidence; it never boosts it.
            cap=min(cap,score)
            if score < 100:
                warnings.append("provider_coverage_score_"+str(round(score,1)))

        ms=summary.get("missing_sources")
        if isinstance(ms,list) and ms:
            missing_sources.extend(str(x) for x in ms[:16])
            warnings.append("provider_missing_sources:"+",".join(str(x) for x in ms[:8]))

        pv=classify_provider_status(overall)
        if pv=="BAD":
            reasons.append("provider_health_"+overall.lower())
        elif pv=="DEGRADED":
            warnings.append("provider_health_"+overall.lower())
            cap=min(cap,float(cfg.get("degraded_confidence_cap",45)))
        elif pv=="UNKNOWN":
            warnings.append("provider_health_schema_unknown")
            cap=min(cap,60.0)

    return {
        "ok":not reasons,
        "reasons":reasons,
        "warnings":warnings,
        "confidence_cap":round(max(0.0,min(100.0,cap)),2),
        "atomic_evidence_endpoint":atomic,
        "atomic_age_seconds":round(age,2) if age is not None else None,
        "market_observation_age_seconds":round(data_age,2) if data_age is not None else None,
        "freshness_basis":"market_observation" if data_age is not None else "response_envelope_only",
        "snapshot_status":snap_status or None,
        "forecast_status":fc_status or None,
        "snapshot_status_verdict":classify_atomic_status(snap_status),
        "forecast_status_verdict":classify_atomic_status(fc_status),
        "provider_score":provider_score,
        "missing_sources":sorted(set(missing_sources)),
    }
