from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.network import assert_loopback_url, NetworkPolicyError
for u in ("http://127.0.0.1:8001","http://localhost:11434","http://[::1]:8001"):
    assert_loopback_url(u)
failed=False
try:
    assert_loopback_url("https://example.com/v1")
except NetworkPolicyError:
    failed=True
assert failed
print("PASS test_network_policy")
