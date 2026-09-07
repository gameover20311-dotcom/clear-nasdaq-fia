from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence_intelligence import cluster_correlated,evidence_cluster_map
from fia_brain.ensemble import aggregate

# Same QQQ object: one provenance family.
qqq=[
 {'evidence_id':'E1','source':'/api/dashboard','path':'live.snapshot.data.QQQ.price','value':500.0},
 {'evidence_id':'E2','source':'/api/dashboard','path':'live.snapshot.data.QQQ.change_pct','value':1.2},
 {'evidence_id':'E3','source':'/api/dashboard','path':'live.snapshot.data.QQQ.direction','value':'UP'},
]
assert len(cluster_correlated(qqq))==1,cluster_correlated(qqq)

# Independent top-level drivers under the broad data object must NOT collapse together.
independent=[
 {'evidence_id':'D1','source':'/api/dashboard','path':'live.snapshot.data.dxy_value','value':97.2},
 {'evidence_id':'D2','source':'/api/dashboard','path':'live.snapshot.data.us10y_value','value':4.2},
 {'evidence_id':'D3','source':'/api/dashboard','path':'live.snapshot.data.nq_structure','value':'UP'},
]
clusters=cluster_correlated(independent)
assert len(clusters)==3,clusters

# Cluster-aware weighting still neutralizes duplicated QQQ leaf votes.
recs=qqq+[{'evidence_id':'E9','source':'/api/dashboard','path':'live.snapshot.data.DXY.value','value':97.2}]
cm=evidence_cluster_map(recs)
a={'direction':'BULLISH','bullish_probability':80,'bearish_probability':20,'confidence':80,'evidence_ids':['E1','E2','E3'],'counter_evidence_ids':[],'unknowns':[]}
b={'direction':'BEARISH','bullish_probability':20,'bearish_probability':80,'confidence':80,'evidence_ids':['E9'],'counter_evidence_ids':[],'unknowns':[]}
out=aggregate([a,b],{'E1','E2','E3','E9'},cm)
assert out['bullish_probability']==50.0,out
print('PASS test_rc2_merge_correlation_provenance')
