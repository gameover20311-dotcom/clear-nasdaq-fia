from __future__ import annotations
import json, re
from typing import Any, Dict, List, Set

TOKEN_RE = re.compile(r"[a-z0-9_./:-]+", re.I)
PATH_PART_RE = re.compile(r"[A-Za-z0-9_-]+")
TIME_KEYS = ("timestamp","time","updated","fresh","age","as_of","captured","release")

# Provenance-aware families: only collapse fields when we can identify the SAME
# instrument/object conservatively. Broad siblings such as data.dxy_value and
# data.us10y_value must remain independent.
INSTRUMENT_TOKENS = {
    "NQ","QQQ","SPY","SPX","DXY","US10Y","TNX","VIX",
    "NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOG","GOOGL","TSLA",
    "AMD","MU","INTC","QCOM","SMCI","NFLX",
}
LEAF_MEASURES = {
    "price","last","close","open","high","low","change","change_pct","change_percent",
    "direction","signal","score","trend","momentum","value","volume","freshness","status",
    "timestamp","updated_at","age_seconds","age_minutes","source","source_quality",
}
DYNAMIC_OBJECT_MARKERS = {"mega_cap_details","events","instruments","symbols"}

def correlation_family(record: Dict[str, Any]) -> str:
    source=str(record.get("source","")).strip().lower()
    parts=PATH_PART_RE.findall(str(record.get("path","") or ""))
    lower=[x.lower() for x in parts]; upper=[x.upper() for x in parts]
    for i,tok in enumerate(upper):
        if tok in INSTRUMENT_TOKENS:
            return source+"|"+".".join(lower[:i+1])
    for marker in DYNAMIC_OBJECT_MARKERS:
        if marker in lower:
            i=lower.index(marker)
            if i+1 < len(lower):
                return source+"|"+".".join(lower[:i+2])
    if len(lower) >= 4 and lower[-1] in LEAF_MEASURES:
        return source+"|"+".".join(lower[:-1])
    return ""

def _tokens(record: Dict[str, Any]) -> Set[str]:
    text = " ".join([
        str(record.get("source","")),
        str(record.get("path","")),
        str(record.get("value",""))[:700],
    ]).lower()
    return set(TOKEN_RE.findall(text))

def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    return len(a & b) / max(1, len(a | b))

def cluster_correlated(records: List[Dict[str, Any]], threshold: float = 0.72) -> List[List[str]]:
    n=len(records)
    if not n: return []
    parent=list(range(n))
    toks=[_tokens(r) for r in records]
    fam=[correlation_family(r) for r in records]
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb: parent[rb]=ra
    for i in range(n):
        for j in range(i):
            same_family=bool(fam[i]) and fam[i]==fam[j]
            if same_family or _jaccard(toks[i],toks[j])>=threshold:
                union(i,j)
    groups={}
    for i,r in enumerate(records):
        groups.setdefault(find(i),[]).append(str(r.get("evidence_id")))
    return list(groups.values())

def evidence_cluster_map(records: List[Dict[str, Any]], threshold: float = 0.72) -> Dict[str,str]:
    out={}
    for idx,ids in enumerate(cluster_correlated(records,threshold),1):
        cid=f"C{idx:03d}"
        for eid in ids: out[str(eid)]=cid
    return out

def freshness_hint(record: Dict[str, Any]) -> str:
    p = str(record.get("path","" )).lower()
    v = record.get("value")
    if any(k in p for k in TIME_KEYS):
        s = str(v).lower()
        if "stale" in s: return "STALE"
        if "fresh" in s or "live" in s: return "FRESH"
        if isinstance(v, (int,float)):
            try:
                x=float(v)
                if "age_seconds" in p:
                    if x<=900:return "FRESH"
                    if x<=3600:return "AGING"
                    return "STALE"
                if "age_minutes" in p:
                    if x<=15:return "FRESH"
                    if x<=60:return "AGING"
                    return "STALE"
                if "age_hours" in p:
                    if x<=0.25:return "FRESH"
                    if x<=1.0:return "AGING"
                    return "STALE"
                # Unitless age is ambiguous and must not be guessed.
                if "age" in p:
                    return "UNKNOWN"
            except Exception: pass
    return "UNKNOWN"

def build_fact_cards(ledger: Dict[str, Any], max_cards: int = 120) -> Dict[str, Any]:
    records=list(ledger.get("records", []))
    cluster_of=evidence_cluster_map(records)
    cards=[]
    for r in records:
        eid=str(r.get("evidence_id")); val=r.get("value")
        if isinstance(val,str): val=" ".join(val.replace("\x00"," ").split())[:500]
        cards.append({"evidence_id":eid,"cluster_id":cluster_of.get(eid),"source":r.get("source"),"path":r.get("path"),"value":val,"freshness_hint":freshness_hint(r)})
        if len(cards)>=max_cards: break
    return {"cards":cards,"cluster_count":len(set(cluster_of.values())),"record_count":len(records),"cluster_of":cluster_of}

def fact_card_text(cards: Dict[str, Any]) -> str:
    lines=[]
    for c in cards.get("cards",[]):
        lines.append(f'{c["evidence_id"]} | {c["cluster_id"]} | {c["freshness_hint"]} | {c["source"]} | {c["path"]} = {json.dumps(c["value"],ensure_ascii=False)}')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# L-9 FIX: VALIDATOR EVIDENCE WINDOW MUST BE A SUPERSET OF WHAT IT VALIDATES
# ---------------------------------------------------------------------------
# Observed in a real 3h14m gpt-oss:20b run: all three judges raised fatal flags
# reading "Unsupported evidence references (e.g. E0091, E0090, E0089 ...)" and the
# tribunal refused to publish. Those citations were NOT hallucinated. Specialists read
# domain_text(ledger, domain, max_records=N) -- a WIDER view of the same ledger -- while
# judges were handed only the fact-card `compact` view. The judges were therefore asked
# to validate citations against an evidence window narrower than the window the cited
# stage was actually given, so correct citations looked unsupported.
#
# Fix: before a validator (skeptic / judge) reviews material, append an explicit
# appendix resolving every evidence id that appears in the material but is absent from
# its base view. The validator can then verify every citation it is asked to judge.
# Ids that exist in NEITHER the view NOR the ledger stay unresolved and are listed, so
# genuine hallucination is still detectable.
import re as _re

_EVIDENCE_ID_RE = _re.compile(r"\bE\d{4}\b")


def _ledger_index(ledger: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for r in (ledger or {}).get("records", []) or []:
        eid = str(r.get("evidence_id") or "")
        if eid:
            out[eid] = r
    return out


def referenced_evidence_ids(material: Any) -> set:
    """Every E#### id appearing anywhere in the material under review."""
    try:
        blob = material if isinstance(material, str) else json.dumps(material, ensure_ascii=False, default=str)
    except Exception:
        blob = str(material)
    return set(_EVIDENCE_ID_RE.findall(blob))


def validator_evidence_view(base_view: str, material: Any, ledger: Dict[str, Any],
                            max_appendix_chars: int = 12000) -> Dict[str, Any]:
    """Return a validator view that covers every citation in `material`.

    Never fabricates evidence: appendix lines are rendered from the real ledger record.
    """
    base = str(base_view or "")
    present = set(_EVIDENCE_ID_RE.findall(base))
    referenced = referenced_evidence_ids(material)
    index = _ledger_index(ledger)

    missing = sorted(referenced - present)
    resolvable = [e for e in missing if e in index]
    unresolvable = [e for e in missing if e not in index]

    lines, used, truncated = [], 0, []
    for eid in resolvable:
        r = index[eid]
        v = r.get("value")
        if isinstance(v, str):
            v = " ".join(v.replace("\x00", " ").split())[:400]
        line = '%s | %s | %s = %s' % (eid, r.get("source"), r.get("path"),
                                      json.dumps(v, ensure_ascii=False, allow_nan=False))
        if used + len(line) + 1 > max_appendix_chars:
            truncated.append(eid)
            continue
        lines.append(line)
        used += len(line) + 1

    view = base
    if lines:
        view = (base
                + "\n\nCITED-EVIDENCE APPENDIX (resolved from the same prediction-time ledger;\n"
                  "these ids were cited by an earlier stage that read a wider ledger view.\n"
                  "They are REAL evidence records and must not be treated as unsupported):\n"
                + "\n".join(lines))
    if unresolvable:
        view = (view
                + "\n\nUNRESOLVED CITED IDS (present in NEITHER the fact cards NOR the ledger --\n"
                  "treat these as genuinely unsupported):\n"
                + ", ".join(unresolvable))

    return {
        "view": view,
        "base_chars": len(base),
        "view_chars": len(view),
        "referenced_ids": len(referenced),
        "already_visible": len(referenced & present),
        "appended_ids": len(lines),
        "unresolvable_ids": unresolvable,
        "appendix_truncated_ids": truncated,
        "coverage_complete": not truncated,
    }
