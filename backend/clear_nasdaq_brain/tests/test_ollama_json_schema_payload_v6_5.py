from pathlib import Path
import sys, json
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import fia_brain.local_llm as llm
from fia_brain.response_schemas import ANALYSIS_SCHEMA

captured={}
class FakeResp:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n):
        return json.dumps({"message":{"content":json.dumps({
            "direction":"NEUTRAL","bullish_probability":50,"bearish_probability":50,
            "confidence":20,"thesis":"x","evidence_ids":[],"counter_evidence_ids":[],
            "unknowns":[],"failure_conditions":[]
        })},"done_reason":"stop"}).encode()
class FakeOpener:
    def open(self,req,timeout=None):
        captured["payload"]=json.loads(req.data.decode())
        return FakeResp()

old=llm.no_proxy_opener
llm.no_proxy_opener=lambda:FakeOpener()
try:
    c=llm.OllamaClient("http://127.0.0.1:11434","gpt-oss:20b")
    out=c.ask_json("s","u",response_schema=ANALYSIS_SCHEMA)
finally:
    llm.no_proxy_opener=old

assert captured["payload"]["format"] == ANALYSIS_SCHEMA
assert captured["payload"]["stream"] is False
assert out["bullish_probability"]==50
print("PASS test_ollama_json_schema_payload_v6_5")
