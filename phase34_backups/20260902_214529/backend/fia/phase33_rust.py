from __future__ import annotations
from typing import Dict

def rust_status()->Dict[str,object]:
    try:
        import fia_phase33_rust  # type: ignore
        return {"status":"AVAILABLE","module":str(fia_phase33_rust),"python_fallback":True}
    except Exception as e:
        return {"status":"SOURCE_INCLUDED_NOT_COMPILED","python_fallback":True,"build_optional":True}
