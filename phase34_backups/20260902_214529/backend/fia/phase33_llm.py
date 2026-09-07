from __future__ import annotations
import json, os
from typing import Any, Dict

def llm_evidence_review(payload: Dict[str,Any], prompt: str="") -> Dict[str,Any]:
    if str(os.getenv("FIA_PHASE33_LLM","0")).lower() not in {"1","true","yes"}:
        return {"status":"DISABLED_BY_DEFAULT","reason":"Set FIA_PHASE33_LLM=1 to enable evidence review; live trading execution is never enabled."}
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key: return {"status":"MISSING_API_KEY"}
    try:
        from google import genai
        client=genai.Client(api_key=key)
        model=os.getenv("FIA_PHASE33_LLM_MODEL","gemini-2.5-flash")
        compact={k:payload.get(k) for k in ("state","direction","decision_strength_0_100","ensemble","news_intelligence","event_surprise","advanced_regime")}
        text=("You are an independent financial evidence critic. Research-only, no trade execution. "
              "Return concise JSON with support, opposition, contradictions, missing_sources, priced_in_risk, and reliability_0_100. "
              f"User prompt: {prompt[:400]}\nEvidence: {json.dumps(compact,default=str)[:12000]}")
        r=client.models.generate_content(model=model,contents=text)
        return {"status":"AVAILABLE","model":model,"text":getattr(r,"text","")[:8000]}
    except Exception as e: return {"status":"ERROR","error":str(e)[:500]}
