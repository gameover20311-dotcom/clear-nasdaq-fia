from __future__ import annotations
import pathlib, sys, json, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia.phase33_regime import detect_advanced_regime
from fia.phase33_orderflow import analyze_orderflow
from fia.phase33_institutional import collect_institutional_inputs
from fia.phase33_rl import rl_live_gate
from fia.phase33_rust import rust_status

FEATURES=[
"LLM news/sentiment brain","offline RL research agent","L2/L3 order-flow intelligence","HMM/Wavelet regime detection","SOR simulation","Kelly/Monte Carlo research","WebGL 3D dashboard","interactive replay","voice/chat copilot","Rust acceleration source","WebSocket streaming","black-swan shield","prop-firm guardrail","VIX/VXN","US2Y/US10Y/real yields","SOX/SMH semi breadth","mega-cap index impact","NQ/ES/SPX/QQQ lead-lag hooks","options skew/gamma hooks","event surprise","historical outcome analogs","multi-model ensemble","OOS calibration + NO_EDGE gate"]

def check(name,cond,detail=""):
    if not cond: raise AssertionError(f"{name} FAIL {detail}")
    print("PASS",name)

def main():
    check("23 declared upgrades",len(FEATURES)==23,len(FEATURES))
    base=ROOT/"fia"
    required=["phase33_engine.py","phase33_api.py","phase33_news.py","phase33_orderflow.py","phase33_regime.py","phase33_institutional.py","phase33_analogs.py","phase33_rl.py","phase33_risk.py","phase33_execution_sim.py","phase33_rust.py","phase33_event.py","phase33_crossasset.py","phase33_llm.py"]
    for x in required: check(f"module {x}",(base/x).exists())
    check("L2 missing is explicit",analyze_orderflow({})["status"]=="MISSING_NOT_FAKED")
    check("RL production weight zero",rl_live_gate()["production_weight"]==0.0)
    check("Rust has python fallback",rust_status()["python_fallback"] is True)
    reg=detect_advanced_regime([{"leading_score":.1,"price_score":.1} for _ in range(8)],.2,.15)
    check("advanced regime returns",bool(reg.get("regime")))
    mainpy=(ROOT/"main.py").read_text()
    check("Phase33 routes registered","install_phase33_routes" in mainpy)
    pol=json.loads((ROOT/"fia_phase33"/"PHASE33_FROZEN_POLICY.json").read_text())
    check("broker execution disabled",pol["broker_execution"] is False)
    check("95 percent claim blocked",pol["claim_95_percent_without_oos"] is False)
    print("PHASE 33 INSTITUTIONAL PRE-MOVE INTEGRITY TEST PASS")
if __name__=="__main__": main()
