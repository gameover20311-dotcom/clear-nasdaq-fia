from pathlib import Path
import sys, json

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fia.phase37_final import load_final_policy, final_project_status

def check(name, cond, detail=None):
    if not cond:
        raise AssertionError(f"{name} FAIL {detail}")
    print("PASS", name)

def main():
    p = load_final_policy()
    s = final_project_status()

    check("project build final", p["project_build_final"] is True)
    check("no more feature phases required", p["further_feature_phases_required"] is False)
    check("remaining work is validation/data only",
          set(p["only_remaining_work_category"]) == {"BACKTESTING","FORWARD_VALIDATION","REAL_DATA_COLLECTION"})
    check("base FIA always included", p["candidate_always_include"] == ["BASE_FIA"])
    check("volatility included", "VOLATILITY" in p["candidate_include_groups"])
    check("news novelty included", "NEWS_NOVELTY" in p["candidate_include_groups"])
    check("futures basis included", "FUTURES_BASIS_PROXY" in p["candidate_include_groups"])
    check("leadership semis included", "LEADERSHIP_SEMIS" in p["candidate_include_groups"])
    check("cross asset excluded", "CROSS_ASSET" in p["candidate_exclude_groups"])
    check("rates real yield excluded", "RATES_REAL_YIELD" in p["candidate_exclude_groups"])
    check("licensed feeds fail closed", len(p["licensed_groups_fail_closed"]) >= 3)
    check("production weights unchanged", p["production_weights_changed"] is False)
    check("RL live weight zero", p["rl_live_weight"] == 0.0)
    check("broker execution disabled", p["broker_execution"] is False)
    check("fake accuracy claims blocked", p["fake_accuracy_claims_blocked"] is True)
    check("OOS required for probability claims", p["probability_claim_requires_oos_validation"] is True)
    check("final status API object valid", s["project_build_final"] is True and s["status"]=="FINAL_CODING_FEATURE_LOCK")
    print("PHASE 37 FINAL LOCK INTEGRITY TEST PASS")

if __name__ == "__main__":
    main()
