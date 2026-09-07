from __future__ import annotations
import json, re, urllib.request
from typing import Any, Dict, Optional
from .network import assert_loopback_url, no_proxy_opener

class LocalModelError(RuntimeError):
    pass

def _loads_strict(s: str) -> Any:
    def bad(x): raise ValueError("non-finite JSON constant forbidden: "+x)
    return json.loads(s, parse_constant=bad)

def _balanced_object_candidates(s: str):
    out=[]
    n=len(s)
    i=0
    while i<n:
        if s[i] != "{":
            i+=1
            continue
        start=i
        depth=0
        in_string=False
        escape=False
        j=i
        while j<n:
            ch=s[j]
            if in_string:
                if escape:
                    escape=False
                elif ch=="\\":
                    escape=True
                elif ch=='"':
                    in_string=False
            else:
                if ch=='"':
                    in_string=True
                elif ch=="{":
                    depth+=1
                elif ch=="}":
                    depth-=1
                    if depth==0:
                        out.append(s[start:j+1])
                        i=j
                        break
                    if depth<0:
                        break
            j+=1
        i+=1
    return out

def _extract_json(text: str) -> Dict[str, Any]:
    s=(text or "").strip()
    if len(s)>200000:
        raise LocalModelError("model response too large")
    if s.startswith("```"):
        s=re.sub(r"^```(?:json)?\s*","",s,flags=re.I)
        s=re.sub(r"\s*```$","",s)
    try:
        obj=_loads_strict(s)
        if isinstance(obj,dict):
            return obj
    except Exception:
        pass

    valid=[]
    seen=set()
    for candidate in _balanced_object_candidates(s):
        try:
            obj=_loads_strict(candidate)
        except Exception:
            continue
        if not isinstance(obj,dict):
            continue
        key=json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)
        if key not in seen:
            seen.add(key)
            valid.append(obj)

    if len(valid)==1:
        return valid[0]
    if len(valid)>1:
        raise LocalModelError("model returned multiple distinct parseable JSON objects")
    raise LocalModelError("model did not return one parseable JSON object")

class OllamaClient:
    def __init__(self,base_url: str,model: str,timeout: int=420,num_ctx: int=24576,reasoning_effort: str="high",num_predict: int=3072):
        assert_loopback_url(base_url)
        self.base_url=base_url.rstrip("/"); self.model=str(model); self.timeout=int(timeout); self.num_ctx=int(num_ctx); self.num_predict=int(num_predict)
        if reasoning_effort not in {"low","medium","high"}: raise ValueError("invalid reasoning_effort")
        self.reasoning_effort=reasoning_effort

    def health(self) -> Dict[str, Any]:
        try:
            req=urllib.request.Request(self.base_url+"/api/tags",headers={"Accept":"application/json"})
            with no_proxy_opener().open(req,timeout=5) as r:
                raw=r.read(2_000_001)
                if len(raw)>2_000_000: raise LocalModelError("health response too large")
                data=_loads_strict(raw.decode("utf-8"))
            models=[m for m in data.get("models",[]) if isinstance(m,dict)]
            names=[str(m.get("name") or m.get("model") or "") for m in models]
            matched=next((m for m in models if str(m.get("name") or m.get("model") or "")==self.model),None)
            exact=matched is not None
            return {
                "ok":True,"model_present":exact,"expected_model":self.model,"models":names[:50],
                "model_digest":str((matched or {}).get("digest") or "") or None,
                "model_size":(matched or {}).get("size"),
                "model_details":(matched or {}).get("details") if isinstance((matched or {}).get("details"),dict) else {},
            }
        except Exception as e:
            return {"ok":False,"model_present":False,"error":type(e).__name__+": "+str(e)[:300]}

    def ask_json(self,system: str,user: str,temperature: float=0.1,seed: int=0,
                 reasoning_effort: Optional[str]=None, timeout: Optional[int]=None,
                 num_ctx: Optional[int]=None, num_predict: Optional[int]=None,
                 response_schema: Optional[Dict[str,Any]]=None) -> Dict[str, Any]:
        t=float(temperature)
        if not 0.0 <= t <= 2.0: raise ValueError("temperature outside [0,2]")
        effort=reasoning_effort or self.reasoning_effort
        if effort not in {"low","medium","high"}: raise ValueError("invalid reasoning_effort")
        ctx=int(num_ctx if num_ctx is not None else self.num_ctx)
        predict=int(num_predict if num_predict is not None else self.num_predict)
        if not 4096 <= ctx <= 131072: raise ValueError("num_ctx outside safe range")
        if not 256 <= predict <= 8192: raise ValueError("num_predict outside safe range")
        if response_schema is not None and not isinstance(response_schema,dict):
            raise ValueError("response_schema must be a dict")
        if response_schema is not None:
            encoded_schema=json.dumps(response_schema,allow_nan=False,separators=(",",":"))
            if len(encoded_schema)>100000:
                raise ValueError("response_schema too large")
        payload={
            "model":self.model,"stream":False,
            "format":response_schema if response_schema is not None else "json",
            "think":effort,
            "messages":[{"role":"system","content":str(system)},{"role":"user","content":str(user)}],
            "options":{"temperature":t,"num_ctx":ctx,"num_predict":predict,"seed":int(seed)},
        }
        raw=json.dumps(payload,allow_nan=False).encode("utf-8")
        req=urllib.request.Request(self.base_url+"/api/chat",data=raw,headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
        try:
            with no_proxy_opener().open(req,timeout=int(timeout if timeout is not None else self.timeout)) as r:
                body=r.read(20_000_001)
                if len(body)>20_000_000: raise LocalModelError("Ollama response too large")
                response=_loads_strict(body.decode("utf-8"))
        except Exception as e:
            raise LocalModelError(type(e).__name__+": "+str(e)[:500]) from e
        message=((response or {}).get("message") or {})
        content=(message.get("content") or "")
        try:
            return _extract_json(content)
        except LocalModelError as e:
            done_reason=str((response or {}).get("done_reason") or "unknown")
            # Never expose or parse message.thinking: it can contain draft reasoning.
            raise LocalModelError(
                f"{e}; done_reason={done_reason}; content_chars={len(content)}"
            ) from e
