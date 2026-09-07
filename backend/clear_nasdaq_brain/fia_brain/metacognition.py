from __future__ import annotations
from typing import Any, Dict

def assess(consensus: Dict[str,Any], tribunal: Dict[str,Any], scenarios: Dict[str,Any], regime: Dict[str,Any], memory: Dict[str,Any], interventions: Dict[str,Any], source_quality: Dict[str,Any]) -> Dict[str,Any]:
    spread=max(0.0,min(100.0,float(consensus.get("probability_spread_std",0))))
    disagreement=min(100.0,spread*3.0)
    grounding=100.0-max(0.0,min(100.0,float(tribunal.get("grounding_score",0))))
    causal=100.0-max(0.0,min(100.0,float(tribunal.get("causal_score",0))))
    uncertainty_judge=100.0-max(0.0,min(100.0,float(tribunal.get("uncertainty_score",0))))
    novelty=min(100.0,max(0.0,float(regime.get("novelty_score",0))*15.0)) if regime.get("enabled") else 0.0
    scenario=min(100.0,max(0.0,float(scenarios.get("entropy",0))*100.0))
    fragility=70.0 if interventions.get("fragile_to_single_driver") else 0.0
    source=100.0-max(0.0,min(100.0,float(source_quality.get("confidence_cap",100)))) if isinstance(source_quality,dict) else 0.0
    memory_risk=0.0
    rate=memory.get("high_confidence_wrong_rate") if isinstance(memory,dict) else None
    if rate is not None: memory_risk=max(0.0,min(100.0,float(rate)*200.0))
    comps={"model_disagreement":round(disagreement,2),"grounding_uncertainty":round(grounding,2),"causal_uncertainty":round(causal,2),"judge_uncertainty":round(uncertainty_judge,2),"regime_novelty":round(novelty,2),"scenario_entropy":round(scenario,2),"single_driver_fragility":round(fragility,2),"source_uncertainty":round(source,2),"failure_memory_risk":round(memory_risk,2)}
    overall=max(comps.values()) if comps else 0.0
    # Metacognition may only reduce confidence, never create direction.
    cap=max(25.0,100.0-overall*0.75)
    return {"components":comps,"overall_uncertainty":round(overall,2),"confidence_cap":round(cap,2),"high_uncertainty":overall>=60.0}
