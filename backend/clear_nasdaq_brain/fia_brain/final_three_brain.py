from __future__ import annotations
from typing import Any, Dict

from . import prompts
from .three_brain import freeze as freeze_three_brain, verify as verify_three_brain, horizon_candidates, model_independence_metadata, ROLES, HORIZONS
from .domains import domain_text
from .evidence_intelligence import validator_evidence_view
from .causal import validate_causal_graph, CONTRACT as CAUSAL_CONTRACT
from .market_twin import build as build_market_twin, confidence_cap as twin_cap
from .interventions import analyze as analyze_interventions, confidence_cap as intervention_cap
from .hypotheses import validate as validate_hypotheses, pressure as hypothesis_pressure, CONTRACT as HYPOTHESIS_CONTRACT
from .scenarios import validate as validate_scenarios, confidence_cap as scenario_cap, CONTRACT as SCENARIO_CONTRACT
from .precommitment import build as build_precommitment, verify as verify_precommitment
from .ensemble import aggregate, divergence
from .tribunal import combine as combine_judges
from .metacognition import assess as assess_metacognition
from .calibration import load_profile, apply_probability, apply_confidence
from .invariants import final_invariants
from .probability_forge import forge as forge_probability
from .failure_memory import confidence_cap as failure_cap
from .guardrails import fail_closed


def _reconcile_calibrated_direction(chief: Dict[str,Any]) -> Dict[str,Any]:
    out=dict(chief)
    prior=str(out.get("direction","NO_EDGE"))
    p=float(out.get("bullish_probability",50.0))
    calibrated="BULLISH" if p>=56 else ("BEARISH" if p<=44 else "NO_EDGE")
    if prior in {"BULLISH","BEARISH"} and calibrated!=prior:
        out["direction"]="NO_EDGE"
        out["confidence"]=min(float(out.get("confidence",0)),50.0)
        u=list(out.get("unknowns") or [])
        if "calibration_removed_directional_conviction" not in u:
            u.append("calibration_removed_directional_conviction")
        out["unknowns"]=u
    return out


def run(brain, env: Dict[str,Any], ledger: Dict[str,Any], compact: str, ids, cards: Dict[str,Any],
        regime: Dict[str,Any], memory: Dict[str,Any], source_quality: Dict[str,Any], runtime_policy: Dict[str,Any]) -> None:
    """Populate env with the final Three-Brain pipeline.

    Ordering is a security/scientific invariant:
      1) six evidence-only 4H/8H role pipelines;
      2) cryptographic freeze;
      3) hardened advisory intelligence;
      4) separate horizon reconciliation.
    """
    three_raw={}
    seeds={
        (4,"BULL"):4101,(4,"BEAR"):4201,(4,"DISCONFIRMING_CRITIC"):4301,
        (8,"BULL"):8101,(8,"BEAR"):8201,(8,"DISCONFIRMING_CRITIC"):8301,
    }
    for horizon in HORIZONS:
        hk=f"{horizon}h"; three_raw[hk]={}
        for role in ROLES:
            three_raw[hk][role]=brain._ask_analysis(
                f"THREE_BRAIN_{role}_{horizon}H",
                prompts.THREE_BRAIN_INSTRUCTION(role,horizon),
                compact,ids,advisory=None,seed=seeds[(horizon,role)],temp=0.10,
                effort=runtime_policy["forecast"]["effort"],
                timeout=runtime_policy["forecast"]["timeout_seconds"],
                num_ctx=runtime_policy["forecast"]["num_ctx"],
                num_predict=runtime_policy["forecast"]["num_predict"],
            )

    three_freeze=freeze_three_brain(three_raw,ledger.get("ledger_sha256",""),brain.config["model"])
    if not verify_three_brain(three_freeze):
        raise RuntimeError("three-brain pre-reconciliation freeze verification failed")
    model_independence=model_independence_metadata(three_freeze)

    # Hardened V6.6.1 layers are strictly post-freeze advisory intelligence.
    specialists={}
    specialist_seeds={"macro_rates":101,"tech_leadership":211,"market_liquidity":307,"catalyst_freshness":401}
    for d,ins in prompts.SPECIALISTS.items():
        specialists[d]=brain._ask_analysis(
            "SPECIALIST_"+d.upper(),ins,
            domain_text(ledger,d,max_records=int(runtime_policy["specialists"]["max_records"])),ids,
            seed=specialist_seeds[d],temp=0.05,
            effort=runtime_policy["specialists"]["effort"],
            timeout=runtime_policy["specialists"]["timeout_seconds"],
            num_ctx=runtime_policy["specialists"]["num_ctx"],
            num_predict=runtime_policy["specialists"]["num_predict"],
        )

    causal=brain._ask_structured(
        "CAUSAL_GRAPH",prompts.CAUSAL_BUILDER,compact,CAUSAL_CONTRACT,validate_causal_graph,ids,
        seed=12347,effort=runtime_policy["core"]["effort"],timeout=runtime_policy["core"]["timeout_seconds"],
        num_ctx=runtime_policy["core"]["num_ctx"],num_predict=runtime_policy["core"]["num_predict"],
    )
    twin=build_market_twin(causal)
    interventions=analyze_interventions(twin)
    hypotheses=brain._ask_structured(
        "HYPOTHESIS_LEDGER",prompts.HYPOTHESIS_BUILDER,compact,HYPOTHESIS_CONTRACT,validate_hypotheses,ids,
        advisory={"market_twin":twin,"specialists":specialists,"three_brain_freeze_sha256":three_freeze["freeze_sha256"]},
        seed=14009,temp=0.03,effort=runtime_policy["core"]["effort"],timeout=runtime_policy["core"]["timeout_seconds"],
        num_ctx=runtime_policy["core"]["num_ctx"],num_predict=runtime_policy["core"]["num_predict"],
    )
    hp=hypothesis_pressure(hypotheses)

    scenarios_by_horizon={}
    precommitments_by_horizon={}
    consensus_by_horizon={}
    for horizon in HORIZONS:
        hk=f"{horizon}h"
        scenarios_by_horizon[hk]=brain._ask_structured(
            "SCENARIO_LATTICE",prompts.SCENARIO_BUILDER_FOR_HORIZON(horizon),compact,
            SCENARIO_CONTRACT,validate_scenarios,ids,
            advisory={"market_twin":twin,"hypotheses":hypotheses,"three_brain_freeze_sha256":three_freeze["freeze_sha256"]},
            seed=15013+horizon,temp=0.03,effort=runtime_policy["core"]["effort"],
            timeout=runtime_policy["core"]["timeout_seconds"],num_ctx=runtime_policy["core"]["num_ctx"],
            num_predict=runtime_policy["core"]["num_predict"],
        )
        precommitments_by_horizon[hk]=build_precommitment(twin,hypotheses,scenarios_by_horizon[hk],interventions)
        if not verify_precommitment(precommitments_by_horizon[hk]):
            raise RuntimeError(f"{hk} precommitment self-hash mismatch")
        consensus_by_horizon[hk]=aggregate(horizon_candidates(three_freeze,horizon),ids,cards.get("cluster_of") or {})
        consensus_by_horizon[hk]["same_model_agreement_is_independent_evidence"]=False
        consensus_by_horizon[hk]["independent_evidence_basis"]="prediction_time_source_clusters_only"

    skeptic_advisory={
            "three_brain_freeze":three_freeze,"consensus_by_horizon":consensus_by_horizon,
            "market_twin":twin,"hypotheses":hypotheses,"scenarios_by_horizon":scenarios_by_horizon,
            "regime_novelty":regime,"failure_memory":memory,"model_independence":model_independence,
        }
    # L-9: a validator must see every citation it is asked to validate.
    skeptic_view=validator_evidence_view(compact,skeptic_advisory,ledger)
    skeptic=brain._ask_analysis(
        "SKEPTIC_AFTER_THREE_BRAIN_FREEZE",prompts.SKEPTIC,skeptic_view["view"],ids,
        advisory=skeptic_advisory,
        seed=7703,temp=0.10,effort=runtime_policy["forecast"]["effort"],
        timeout=runtime_policy["forecast"]["timeout_seconds"],num_ctx=runtime_policy["forecast"]["num_ctx"],
        num_predict=runtime_policy["forecast"]["num_predict"],
    )

    judge_input={
        "three_brain_freeze":three_freeze,"model_independence":model_independence,
        "specialists":specialists,"causal_graph":causal,"market_twin":twin,"interventions":interventions,
        "hypotheses":hypotheses,"hypothesis_pressure":hp,"scenarios_by_horizon":scenarios_by_horizon,
        "precommitments_by_horizon":precommitments_by_horizon,"consensus_by_horizon":consensus_by_horizon,
        "skeptic":skeptic,"regime_novelty":regime,"failure_memory":memory,
    }
    # L-9 EVIDENCE-WINDOW FIX. Specialists read domain_text(ledger, ..., max_records=N),
    # a WIDER view than the fact-card `compact` the judges were previously given. Judges
    # therefore flagged correct specialist citations as "unsupported evidence references"
    # and the tribunal refused to publish. The judge view is now guaranteed to be a
    # superset of every citation in judge_input.
    judge_view=validator_evidence_view(compact,judge_input,ledger)
    judges=[
        brain._ask_judge(judge_view["view"],judge_input,18101,prompts.JUDGE_ROLES[0],runtime_policy["critics"]),
        brain._ask_judge(judge_view["view"],judge_input,18209,prompts.JUDGE_ROLES[1],runtime_policy["critics"]),
        brain._ask_judge(judge_view["view"],judge_input,18317,prompts.JUDGE_ROLES[2],runtime_policy["critics"]),
    ]
    tribunal=combine_judges(judges)

    horizon_results={}
    overall_ok=True
    profile=load_profile(brain.config.get("calibration_profile","")) if brain.config.get("calibration_profile") else None
    for horizon in HORIZONS:
        hk=f"{horizon}h"
        consensus=consensus_by_horizon[hk]
        scenarios=scenarios_by_horizon[hk]
        advisory={
            "frozen_three_brain_horizon":three_freeze["cells"][hk],
            "three_brain_freeze_sha256":three_freeze["freeze_sha256"],
            "model_independence":model_independence,
            "specialists":specialists,"causal_graph":causal,"market_twin":twin,"interventions":interventions,
            "hypotheses":hypotheses,"hypothesis_pressure":hp,"scenarios":scenarios,
            "precommitment":precommitments_by_horizon[hk],"same_model_consensus":consensus,
            "skeptic":skeptic,"tribunal":tribunal,"regime_novelty":regime,"failure_memory":memory,
        }
        chief=brain._ask_analysis(
            f"CHIEF_FIA_{horizon}H",prompts.CHIEF_THREE_BRAIN(horizon),compact,ids,advisory=advisory,
            seed=18807+horizon,temp=0.04,effort=runtime_policy["core"]["effort"],
            timeout=runtime_policy["core"]["timeout_seconds"],num_ctx=runtime_policy["core"]["num_ctx"],
            num_predict=runtime_policy["core"]["num_predict"],
        )
        div=divergence(chief,consensus)
        meta=assess_metacognition(consensus,tribunal,scenarios,regime,memory,interventions,source_quality or {})
        caps=[float(tribunal["recommended_confidence_cap"]),float(consensus["confidence"])+10,float(meta["confidence_cap"])]
        if isinstance(source_quality,dict): caps.append(float(source_quality.get("confidence_cap",100)))
        if brain.config.get("market_twin_gate",True):
            caps.append(twin_cap(twin)); caps.append(intervention_cap(interventions))
        if brain.config.get("scenario_entropy_gate",True): caps.append(scenario_cap(scenarios))
        if brain.config.get("novelty_gate",True): caps.append(float(regime.get("confidence_cap",100)))
        if brain.config.get("failure_memory_gate",True): caps.append(failure_cap(memory))
        chief["confidence"]=round(min(float(chief["confidence"]),*caps),2)

        fatal=list(tribunal["fatal_flags"])
        fatal.extend(final_invariants(chief,consensus,tribunal))
        if div["direction_conflict"] and div["probability_gap"]>12:
            fatal.append("chief_direction_conflict_with_same_model_consensus")
        if chief.get("direction")=="BULLISH" and hp["signed_pressure"]<-0.35 and chief["confidence"]>45:
            fatal.append("chief_conflicts_with_precommitted_hypotheses")
        if chief.get("direction")=="BEARISH" and hp["signed_pressure"]>0.35 and chief["confidence"]>45:
            fatal.append("chief_conflicts_with_precommitted_hypotheses")

        pf={"engine":"SOL56_PROBABILITY_FORGE_V7_2","status":"NOT_RUN","horizon_hours":horizon}
        hstatus="OK"
        if fatal:
            chief=fail_closed(f"V7.4 {horizon}H tribunal/precommitment/invariant rejection: "+"; ".join(sorted(set(fatal))[:8]),evidence_ids=consensus.get("evidence_ids",[]))
            hstatus="FAIL_CLOSED"; overall_ok=False; pf["status"]="SKIPPED_UPSTREAM_FATAL"
        else:
            pb=apply_probability(float(chief["bullish_probability"]),profile)
            chief["bullish_probability"]=round(pb,2); chief["bearish_probability"]=round(100-pb,2)
            chief["confidence"]=round(apply_confidence(chief["confidence"],profile),2)
            chief=_reconcile_calibrated_direction(chief)
            post_fail=final_invariants(chief,consensus,tribunal)
            if post_fail:
                chief=fail_closed(f"post-calibration {horizon}H invariant rejection: "+"; ".join(sorted(set(post_fail))[:8]),evidence_ids=consensus.get("evidence_ids",[]))
                hstatus="FAIL_CLOSED"; overall_ok=False; pf["status"]="SKIPPED_POST_CALIBRATION_FATAL"
            else:
                chief,pf=forge_probability(chief,consensus,scenarios,tribunal,meta,interventions,source_quality or {},cards.get("cluster_of") or {},profile)
                pf=dict(pf); pf["horizon_hours"]=horizon
                post_forge_fail=final_invariants(chief,consensus,tribunal)
                if post_forge_fail:
                    chief=fail_closed(f"post-probability-forge {horizon}H invariant rejection: "+"; ".join(sorted(set(post_forge_fail))[:8]),evidence_ids=consensus.get("evidence_ids",[]))
                    hstatus="FAIL_CLOSED"; overall_ok=False; pf["status"]="REJECTED_BY_POST_FORGE_INVARIANTS"
                else:
                    pf["status"]="APPLIED"

        horizon_results[hk]={
            "status":hstatus,"horizon_hours":horizon,"final":chief,"same_model_consensus":consensus,
            "scenarios":scenarios,"precommitment":precommitments_by_horizon[hk],"chief_vs_consensus":div,
            "metacognition":meta,"probability_forge":pf,"confidence_caps":caps,
        }

    env["status"]="OK" if overall_ok else "FAIL_CLOSED"
    env["primary_horizon_hours"]=8
    env["final_by_horizon"]={k:v["final"] for k,v in horizon_results.items()}
    env["final"]=horizon_results["8h"]["final"]
    env["passes"]={
        "three_brain_freeze":three_freeze,
        "three_brain_by_horizon":{k:[three_freeze["cells"][k][r]["analysis"] for r in ROLES] for k in ("4h","8h")},
        "model_independence":model_independence,
        "specialists":specialists,"causal_graph":causal,"market_twin":twin,"interventions":interventions,
        "hypotheses":hypotheses,"hypothesis_pressure":hp,
        "scenarios_by_horizon":scenarios_by_horizon,"precommitments_by_horizon":precommitments_by_horizon,
        "consensus_by_horizon":consensus_by_horizon,"skeptic":skeptic,"judges":judges,"tribunal":tribunal,
        "validator_evidence_window":{
            "policy":"validator view is a superset of every citation it validates (L-9)",
            "skeptic":{k:v for k,v in skeptic_view.items() if k!="view"},
            "judges":{k:v for k,v in judge_view.items() if k!="view"},
        },
        "horizon_results":horizon_results,
        # Backward-compatible primary 8H aliases.
        "candidates":horizon_candidates(three_freeze,8),
        "counterfactuals":{"bull_case":three_freeze["cells"]["8h"]["BULL"]["analysis"],"bear_case":three_freeze["cells"]["8h"]["BEAR"]["analysis"]},
        "consensus":consensus_by_horizon["8h"],"scenarios":scenarios_by_horizon["8h"],
        "precommitment":precommitments_by_horizon["8h"],
        "chief_vs_consensus":horizon_results["8h"]["chief_vs_consensus"],
        "metacognition":horizon_results["8h"]["metacognition"],
        "probability_forge":horizon_results["8h"]["probability_forge"],
        "confidence_caps":horizon_results["8h"]["confidence_caps"],
    }
