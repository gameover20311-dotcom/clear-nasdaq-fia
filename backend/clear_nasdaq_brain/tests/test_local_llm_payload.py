from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.local_llm import OllamaClient,_extract_json
c=OllamaClient("http://127.0.0.1:11434","gpt-oss:20b",reasoning_effort="high")
assert c.reasoning_effort=="high" and _extract_json('{"x":1}')["x"]==1
try: _extract_json('{"x":NaN}'); raise AssertionError("NaN accepted")
except Exception: pass
print("PASS test_local_llm_payload")
