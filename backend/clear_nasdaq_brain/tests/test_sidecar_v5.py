from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.network import assert_loopback_url,NetworkPolicyError
assert_loopback_url('http://127.0.0.1:8765'); bad=False
try:assert_loopback_url('http://0.0.0.0:8765')
except NetworkPolicyError:bad=True
assert bad
text=(ROOT/'fia_brain/sidecar.py').read_text(encoding='utf-8'); assert 'V7.4 FINAL THREE-BRAIN SIDECAR' in text
print('PASS test_sidecar_v5')
