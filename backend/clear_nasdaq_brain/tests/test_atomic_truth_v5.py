from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import fia_brain.evidence as e
calls=[]
def fake(url,timeout=8,max_bytes=4000000):
    calls.append(url)
    if url.endswith("/api/fia/dashboard"):
        return 200,{"ok":True,"generated_at":"2026-09-03T12:00:00+00:00","live":{"forecast":{"status":"LIVE"}}}
    return 200,{"overall":"LIVE","secret_health_only_value":"MUST_NOT_ENTER_LEDGER"}
old=e.http_json; e.http_json=fake
try:
    s=e.collect_atomic("http://127.0.0.1:8001","/api/fia/dashboard",["/api/fia/provider-health"],2)
    led=e.build_ledger(s,100,100000)
    assert set(s["payloads"])=={"/api/fia/dashboard"}
    assert "/api/fia/provider-health" in s["health_payloads"]
    text=e.evidence_text(led)
    assert "MUST_NOT_ENTER_LEDGER" not in text
finally:
    e.http_json=old
print("PASS test_atomic_truth_v5")
