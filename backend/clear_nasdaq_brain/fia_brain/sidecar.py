from __future__ import annotations
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit
from .config import load
from .ledger import verify
from .network import assert_loopback_url
from .orchestrator import FIABrain

def _tail_last_line(path: Path,max_bytes: int=1_000_000) -> Optional[bytes]:
    if not path.exists() or path.stat().st_size==0: return None
    with path.open("rb") as f:
        size=f.seek(0,os.SEEK_END); pos=size; data=b""
        while pos>0 and len(data)<max_bytes:
            step=min(4096,pos); pos-=step; f.seek(pos); data=f.read(step)+data
            lines=[x for x in data.splitlines() if x.strip()]
            if len(lines)>=2 or pos==0:
                return lines[-1] if lines else None
    raise ValueError("last ledger row exceeds max_bytes")

def serve(host: str="127.0.0.1",port: int=8765,config_path: Optional[str]=None) -> None:
    assert_loopback_url("http://%s:%d"%(host,int(port)))
    cfg=load(config_path); brain=FIABrain(cfg)

    class H(BaseHTTPRequestHandler):
        server_version="FIABrainV74"
        def _send(self,code: int,obj: Any):
            raw=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        def log_message(self,fmt,*args): return
        def _path(self): return urlsplit(self.path).path
        def do_GET(self):
            path=self._path()
            if path=="/health":
                mh=brain.client.health(); ls=verify(cfg["shadow_ledger"],require_anchor=True)
                ok=bool(mh.get("ok") and mh.get("model_present") and ls.get("ok"))
                self._send(200 if ok else 503,{"ok":ok,"service":"CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN SIDECAR",
                    "model_health":mh,"shadow_ledger":ls,"base_fia_modified":False,
                    "forward_oos_modified":False,"paid_api_used":(False if brain.provider=="ollama" else None),"hosted_api_used":(brain.provider!="ollama")}); return
            if path=="/last":
                ledger_path=Path(cfg["shadow_ledger"])
                integrity=verify(ledger_path,require_anchor=True)
                if not integrity.get("ok"):
                    self._send(503,{"ok":False,"error":"shadow_ledger_integrity_failed","integrity":integrity}); return
                try: raw=_tail_last_line(ledger_path)
                except Exception as e:
                    self._send(500,{"ok":False,"error":"ledger_read_failed","type":type(e).__name__}); return
                if raw is None: self._send(404,{"ok":False,"reason":"no shadow records"}); return
                try: obj=json.loads(raw.decode("utf-8"))
                except Exception: self._send(500,{"ok":False,"error":"invalid_last_ledger_row"}); return
                self._send(200,obj); return
            self._send(404,{"ok":False})
        def do_POST(self):
            if self._path()!="/analyze": self._send(404,{"ok":False}); return
            try:
                out=brain.analyze(write_shadow=True)
                self._send(200 if out.get("status")=="OK" else 503,out)
            except Exception as e:
                self._send(500,{"ok":False,"error":"analysis_failed","type":type(e).__name__})

    server=ThreadingHTTPServer((host,int(port)),H)
    print(f"FIA BRAIN V7.4 FINAL THREE-BRAIN sidecar listening on http://{host}:{port}")
    server.serve_forever()
