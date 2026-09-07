from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.evidence_genome import build
l={'ledger_sha256':'x','records':[{'evidence_id':'E1','source':'/api/fia/dashboard','path':'macro.us10y','value':4.2},{'evidence_id':'E2','source':'/api/fia/dashboard','path':'tech.nvda','value':'strong'}]}
a=build(l); l['records'][0]['value']=5.1; b=build(l); assert a['evidence_genome_sha256']!=b['evidence_genome_sha256']
print('PASS test_genome_v6')
