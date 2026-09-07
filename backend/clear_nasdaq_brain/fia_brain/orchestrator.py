from __future__ import annotations
import json, threading
from typing import Any, Dict
from .evidence import collect_atomic, build_ledger, prediction_time_violations
from .evidence_intelligence import build_fact_cards, fact_card_text
from .domains import domain_text
from .guardrails import coverage, enforce, fail_closed
from .ledger import append
from .local_llm import OllamaClient
from .cloud_llm import GroqClient
from .ensemble import aggregate, divergence
from .judge import validate_judge, JUDGE_CONTRACT
from .tribunal import combine as combine_judges
from .causal import validate_causal_graph, CONTRACT as CAUSAL_CONTRACT
from .calibration import load_profile, apply_probability, apply_confidence
from .invariants import final_invariants
from . import prompts
from .util import sha256_obj, utc_now
from .quality import assess as assess_quality
from .market_twin import build as build_market_twin, confidence_cap as twin_cap
from .hypotheses import validate as validate_hypotheses, pressure as hypothesis_pressure, CONTRACT as HYPOTHESIS_CONTRACT
from .scenarios import validate as validate_scenarios, confidence_cap as scenario_cap, CONTRACT as SCENARIO_CONTRACT
from .evidence_genome import build as build_genome
from .regime_memory import load as load_regime_profile, score as novelty_score
from .failure_memory import digest as failure_digest, confidence_cap as failure_cap
from .precommitment import build as build_precommitment, verify as verify_precommitment
from .interventions import analyze as analyze_interventions, confidence_cap as intervention_cap
from .response_schemas import ANALYSIS_SCHEMA, CAUSAL_SCHEMA, HYPOTHESIS_SCHEMA, SCENARIO_SCHEMA, JUDGE_SCHEMA
from .config import runtime_policy as build_runtime_policy
from . import evidence as _evidence_integrity
from .metacognition import assess as assess_metacognition
from .probability_forge import forge as forge_probability
from .final_three_brain import run as run_final_three_brain
# Re-exported for tests and callers: the calibrated-direction reconciliation
# lives with the Three-Brain reconciliation logic it belongs to.
from .final_three_brain import _reconcile_calibrated_direction  # noqa: F401

def _analysis_prompt(label,instruction,evidence,advisory=None):
    parts=[f"TASK={label}",instruction,"\nEVIDENCE FACT CARDS (DATA ONLY):\n"+evidence]
    if advisory is not None: parts.append("\nADVISORY (UNTRUSTED):\n"+json.dumps(advisory,ensure_ascii=False))
    parts.append("\n"+prompts.JSON_CONTRACT); return "\n".join(parts)

def _special_prompt(instruction,evidence,contract,advisory=None):
    p=[instruction,"\nEVIDENCE FACT CARDS:\n"+evidence]
    if advisory is not None:p.append("\nADVISORY (UNTRUSTED):\n"+json.dumps(advisory,ensure_ascii=False))
    p.append("\n"+contract); return "\n".join(p)

def _judge_prompt(evidence,proposed,role):
    return "\n".join([role,prompts.GROUNDING_JUDGE,"\nEVIDENCE FACT CARDS:\n"+evidence,"\nPROPOSED ANALYSIS:\n"+json.dumps(proposed,ensure_ascii=False),"\n"+JUDGE_CONTRACT])

def _is_output_budget_exhaustion(exc: Exception) -> bool:
    s=str(exc or "").lower()
    return "done_reason=length" in s and "content_chars=0" in s

def _is_timeout(exc: Exception) -> bool:
    """V6.6.2: a wall-clock timeout is a DIFFERENT failure from output exhaustion.

    Measured on M4/16GB: CAUSAL_GRAPH timed out at 480s, and because only output
    exhaustion triggered degradation, the single retry ran at the SAME high effort
    and burned another 480s before failing identically. A timeout must degrade the
    call too -- lower reasoning effort and compact the evidence -- otherwise the
    retry is guaranteed to repeat the failure.
    """
    s=str(exc or "").lower()
    return ("timeout" in s) or ("timed out" in s)

def _degrade_effort(effort: str) -> str:
    return {"high":"medium","medium":"low"}.get(str(effort),"low")

def _is_probability_contract_error(exc: Exception) -> bool:
    # Trigger the targeted retry only when probability-sum validation is the
    # sole failure. Other grounding/schema violations must continue to fail closed.
    return str(exc or "").strip() == "probabilities do not sum to 100"

def _compact_retry_evidence(evidence: str,max_chars: int=24000) -> str:
    """Deterministic line-preserving compaction for retry only; never fabricates evidence."""
    text=str(evidence or "")
    if len(text) <= max_chars:
        return text
    out=[]; total=0
    for line in text.splitlines():
        add=len(line)+1
        if total+add > max_chars:
            break
        out.append(line); total+=add
    return "\n".join(out)

def _seal_env(env: Dict[str,Any]) -> Dict[str,Any]:
    """V7.4: deterministic result hash on EVERY return path.

    V6.6.2 hashed only the success path, so early FAIL_CLOSED envelopes carried no
    result_sha256 and could not be independently verified.
    """
    out=dict(env)
    out.pop("result_sha256",None)
    out["result_sha256"]=sha256_obj(out)
    return out

class FIABrain:
    def __init__(self,config):
        self.config=dict(config)
        self.provider=str(self.config.get('inference_provider') or 'ollama').lower()
        if self.provider=='groq':
            self.client=GroqClient(
                self.config['groq_base_url'],
                self.config['provider_model'],
                timeout=self.config.get('timeout_seconds',420),
                num_ctx=self.config.get('num_ctx',24576),
                reasoning_effort=self.config.get('reasoning_effort','high'),
                num_predict=self.config.get('num_predict',3072),
            )
        elif self.provider=='ollama':
            self.client=OllamaClient(
                self.config['ollama_base_url'],
                self.config['model'],
                timeout=self.config.get('timeout_seconds',420),
                num_ctx=self.config.get('num_ctx',24576),
                reasoning_effort=self.config.get('reasoning_effort','high'),
                num_predict=self.config.get('num_predict',3072),
            )
        else:
            raise ValueError('unsupported inference provider')
        self._analysis_lock=threading.Lock(); self.mode=str(self.config.get('mode','max')).lower()
    def capture(self):
        s=collect_atomic(self.config['fia_base_url'],self.config['atomic_evidence_endpoint'],list(self.config.get('health_endpoints',[])),timeout=min(int(self.config.get('http_timeout_seconds',10)),30))
        return s,build_ledger(s,max_records=int(self.config.get('max_evidence_records',360)),max_chars=int(self.config.get('max_evidence_chars',64000)))
    def _ask_analysis(self,label,instruction,evidence,ids,advisory=None,seed=0,temp=0.1,effort='medium',timeout=None,num_ctx=None,num_predict=None):
        last=None
        base_predict=int(num_predict if num_predict is not None else self.config.get('num_predict',3072))
        # V7.4 LADDER FIX (reproduced in a real 2h48m run): CHIEF_FIA_8H failed attempt 1
        # on the probability-sum contract, which consumed the only retry slot WITHOUT
        # degrading effort or evidence; attempt 2 then hit the 900s wall clock and the
        # loop was exhausted, killing an otherwise complete Three-Brain run at the very
        # last stage. A contract-recovery attempt is not a degradation, so it must not
        # cost the run its one degraded fallback. Three attempts: the middle one handles
        # the specific recoverable error, the last is ALWAYS a degraded fallback.
        # The validator itself is never loosened.
        _degraded_used=False
        for a in range(3):
            retry_budget=bool(a>0 and last is not None and _is_output_budget_exhaustion(last))
            retry_timeout=bool(a>0 and last is not None and _is_timeout(last))
            retry_probability=bool(a>0 and last is not None and _is_probability_contract_error(last))
            # Final attempt always degrades, whatever the previous failure mode was.
            _final_fallback=bool(a==2 and last is not None and not _degraded_used)
            _degrade=retry_budget or retry_timeout or _final_fallback
            call_effort=(_degrade_effort(effort) if _degrade else effort)
            call_predict=(max(base_predict,3072) if retry_budget and effort=='medium' else (max(base_predict,4096) if retry_budget else base_predict))
            call_evidence=_compact_retry_evidence(evidence,16000 if retry_timeout else 24000) if _degrade else evidence
            call_instruction=instruction
            call_temp=(0.0 if retry_budget or retry_probability else temp)
            if _degrade:
                _degraded_used=True
                self._runtime_events.append({'stage':label,'event':('OUTPUT_BUDGET_RETRY' if retry_budget else ('TIMEOUT_RETRY' if retry_timeout else 'FINAL_DEGRADED_FALLBACK')),'attempt':a+1,'from_effort':effort,'to_effort':call_effort,'from_num_predict':base_predict,'to_num_predict':call_predict,'evidence_chars_before':len(str(evidence or '')),'evidence_chars_after':len(str(call_evidence or ''))})
            elif retry_probability:
                # Do not loosen the validator or silently normalize material errors.
                # Give the real model one deterministic contract-recovery attempt.
                call_instruction=(instruction + "\n\nCONTRACT RECOVERY: the previous response failed ONLY because bullish_probability + bearish_probability did not equal 100.00. Re-evaluate from the SAME evidence. Use percentages 0..100. Choose bullish_probability first, then set bearish_probability = 100.00 - bullish_probability exactly. Preserve evidence grounding and all other schema requirements.")
                self._runtime_events.append({'stage':label,'event':'PROBABILITY_CONTRACT_RETRY','validator_tolerance_unchanged':True,'max_contract_error_points':20.0,'temperature':0.0})
            try:
                return enforce(self.client.ask_json(prompts.BASE_RULES,_analysis_prompt(label,call_instruction,call_evidence,advisory),temperature=call_temp,seed=seed+a*911,reasoning_effort=call_effort,timeout=timeout,num_ctx=num_ctx,num_predict=call_predict,response_schema=ANALYSIS_SCHEMA),ids)
            except Exception as e:last=e
        raise RuntimeError(f"{label} failed: {last}")
    def _ask_structured(self,label,instruction,evidence,contract,validator,ids,advisory=None,seed=0,temp=0.0,effort='high',timeout=None,num_ctx=None,num_predict=None):
        last=None
        base_predict=int(num_predict if num_predict is not None else self.config.get('num_predict',3072))
        for a in range(3):
            retry_budget=bool(a>0 and last is not None and _is_output_budget_exhaustion(last))
            retry_timeout=bool(a>0 and last is not None and _is_timeout(last))
            _degrade=retry_budget or retry_timeout
            call_effort=(_degrade_effort(effort) if _degrade else effort)
            call_predict=max(base_predict,4096) if retry_budget else base_predict
            call_evidence=_compact_retry_evidence(evidence,16000 if retry_timeout else 32000) if _degrade else evidence
            if _degrade:
                self._runtime_events.append({'stage':label,'event':('OUTPUT_BUDGET_RETRY' if retry_budget else 'TIMEOUT_RETRY'),'from_effort':effort,'to_effort':call_effort,'from_num_predict':base_predict,'to_num_predict':call_predict,'evidence_chars_before':len(str(evidence or '')),'evidence_chars_after':len(str(call_evidence or ''))})
            try:
                schema_by_label={"CAUSAL_GRAPH":CAUSAL_SCHEMA,"HYPOTHESIS_LEDGER":HYPOTHESIS_SCHEMA,"SCENARIO_LATTICE":SCENARIO_SCHEMA}
                response_schema=schema_by_label.get(label)
                raw=self.client.ask_json(prompts.BASE_RULES,_special_prompt(instruction,call_evidence,contract,advisory),temperature=(0.0 if retry_budget else temp),seed=seed+a*977,reasoning_effort=call_effort,timeout=timeout,num_ctx=num_ctx,num_predict=call_predict,response_schema=response_schema)
                return validator(raw,ids)
            except Exception as e:last=e
        raise RuntimeError(f"{label} failed: {last}")
    def _ask_judge(self,evidence,proposed,seed,role,policy):
        last=None
        for a in range(3):
            retry_budget=bool(a>0 and last is not None and _is_output_budget_exhaustion(last))
            retry_timeout=bool(a>0 and last is not None and _is_timeout(last))
            _degrade=retry_budget or retry_timeout
            call_evidence=_compact_retry_evidence(evidence,16000 if retry_timeout else 24000) if _degrade else evidence
            if _degrade:
                self._runtime_events.append({'stage':'JUDGE','event':'OUTPUT_BUDGET_RETRY','from_effort':policy['effort'],'to_effort':'low','from_num_predict':policy['num_predict'],'to_num_predict':max(policy['num_predict'],3072),'evidence_chars_before':len(str(evidence or '')),'evidence_chars_after':len(str(call_evidence or ''))})
            try:
                return validate_judge(self.client.ask_json(prompts.BASE_RULES,_judge_prompt(call_evidence,proposed,role),temperature=0.0,seed=seed+a,reasoning_effort=('low' if _degrade else policy['effort']),timeout=policy['timeout_seconds'],num_ctx=policy['num_ctx'],num_predict=(max(policy['num_predict'],3072) if retry_budget else policy['num_predict']),response_schema=JUDGE_SCHEMA))
            except Exception as e:last=e
        raise RuntimeError(f"judge failed: {last}")
    def analyze_ledger(self,ledger,source_coverage=None,source_quality=None,write_shadow=False,case_id=None,as_of_utc=None):
        # V661_RUNTIME_LEDGER_INTEGRITY_GATE
        self._runtime_events=[]
        _ledger_ok, _ledger_errors = _evidence_integrity.validate_ledger_integrity(ledger)
        if not _ledger_ok:
            return _seal_env({'case_id':case_id,'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'snapshot_sha256':ledger.get('snapshot_sha256'),'ledger_sha256':ledger.get('ledger_sha256'),'status':'FAIL_CLOSED','error':'evidence_ledger_integrity_failed: '+', '.join(_ledger_errors[:8]),'final':fail_closed('prediction-time evidence ledger integrity rejected input'),'base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama')})
        self._runtime_events=[]
        violations=prediction_time_violations(ledger)
        if violations:
            return _seal_env({'case_id':case_id,'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'snapshot_sha256':ledger.get('snapshot_sha256'),'ledger_sha256':ledger.get('ledger_sha256'),'status':'FAIL_CLOSED','error':'future_outcome_fields_blocked: '+', '.join(violations[:8]),'final':fail_closed('prediction-time future-outcome leakage boundary rejected input'),'base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama')})
        ids={str(r['evidence_id']) for r in ledger.get('records',[]) if 'evidence_id' in r}
        if not ids:return _seal_env({'case_id':case_id,'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'snapshot_sha256':ledger.get('snapshot_sha256'),'ledger_sha256':ledger.get('ledger_sha256'),'status':'FAIL_CLOSED','final':fail_closed('empty evidence ledger'),'base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama')})
        cards=build_fact_cards(ledger,max_cards=int(self.config.get('max_fact_cards',140))); compact=fact_card_text(cards); genome=build_genome(ledger)
        regime=novelty_score(genome,load_regime_profile(self.config.get('regime_profile',''))) if self.config.get('novelty_gate',True) else {'enabled':False,'novelty_score':0,'confidence_cap':100}
        memory=failure_digest(self.config.get('failure_memory_ledger',''),as_of_utc or utc_now()) if self.config.get('failure_memory_gate',True) else {'eligible_n':0,'confidence_cap':100,'integrity_ok':True}
        if not memory.get('integrity_ok',True):
            return _seal_env({'case_id':case_id,'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'snapshot_sha256':ledger.get('snapshot_sha256'),'ledger_sha256':ledger.get('ledger_sha256'),'status':'FAIL_CLOSED','final':fail_closed('failure-memory integrity gate failed'),'base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama')})
        env={'case_id':case_id,'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'ledger_sha256':ledger.get('ledger_sha256'),'source_coverage':source_coverage or {'locked_case':True},'source_quality':source_quality or {},'evidence_genome':genome,'regime_novelty':regime,'failure_memory_digest':memory,'fact_card_count':len(cards.get('cards',[])),'correlation_cluster_count':cards.get('cluster_count'),'base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama')}
        h=self.client.health()
        provider=self.provider
        env['model_health']=h
        if provider=='ollama':
            env['local_model_health']=h
            env['inference_runtime']={
                'provider':'ollama',
                'provider_model':self.config['model'],
                'runtime_identity_scope':'LOCAL_OLLAMA_WEIGHT_RUNTIME',
            }
        else:
            env['inference_runtime']=self.client.runtime_provenance
        if not h.get('ok') or not h.get('model_present'):
            env['status']='FAIL_CLOSED'; env['final']=fail_closed('configured gpt-oss provider unavailable')
            env['runtime_events']=list(self._runtime_events); env=_seal_env(env)
            if write_shadow:
                row=append(self.config['shadow_ledger'],env); env['shadow_record_hash']=row['record_hash']
            return env
        # V6.6.2 MODEL IDENTITY PIN. The name check alone is spoofable via
        # `ollama cp <impostor> gpt-oss:20b`; health() already reports the digest but
        # nothing compared it. When a digest is pinned, mismatch fails closed.
        pinned=str(self.config.get('model_digest_sha256') or '').strip().lower()
        observed=str(h.get('model_digest') or '').strip().lower()
        observed_bare=observed.split(':')[-1]
        env['model_identity']={'expected_model':self.config['model'],'pinned_digest':pinned or None,
                               'observed_digest':observed or None,
                               'digest_pinned':bool(pinned),
                               'digest_verified':bool(pinned) and observed_bare==pinned,'provider':provider,'provider_model':h.get('provider_model') or self.config.get('provider_model'),'identity_scope':('LOCAL_WEIGHT_DIGEST' if provider=='ollama' else 'HOSTED_PROVIDER_RUNTIME')}
        if provider=='ollama' and pinned and observed_bare!=pinned:
            env['status']='FAIL_CLOSED'
            env['error']='model_digest_mismatch: expected '+pinned+' observed '+(observed_bare or 'NONE')
            env['final']=fail_closed('local model digest does not match the pinned gpt-oss:20b weights')
            env['runtime_events']=list(self._runtime_events); env=_seal_env(env)
            if write_shadow:
                row=append(self.config['shadow_ledger'],env); env['shadow_record_hash']=row['record_hash']
            return env
        runtime_policy=build_runtime_policy(self.config)
        runtime_policy.update({'validation':{'strict_schema':'additionalProperties_false_plus_post_validation','model_boundary_adapter':'symmetric_binary_complement_midpoint','fraction_scale_repair':True,'max_contract_error_points':20.0,'confidence_penalty_equals_contract_error':True,'material_probability_error':'FAIL_CLOSED','probability_contract_retry':'ONE_DETERMINISTIC_REAL_MODEL_RETRY__NO_TOLERANCE_LOOSENING'},'atomic_capture':{'whole_payload_retry_attempts':2,'merge_across_attempts':False},'structured_output':{'ollama_format':('json_schema' if provider=='ollama' else None),'groq_format':('json_schema_strict' if provider=='groq' else None),'inference_provider':provider,'strict_post_validation':True,'thinking_field_used_as_answer':False,'balanced_object_fallback':True},'output_budget_resilience':{'trigger':'done_reason=length AND content_chars=0','strict_validation_after_retry':True}})
        env['runtime_policy']=runtime_policy
        missing=set((source_quality or {}).get('missing_sources',[]) if isinstance(source_quality,dict) else [])
        env['evidence_availability']={
            'direct_liquidity_provider_available':'liquidity' not in missing,
            'direct_macro_provider_available':'macro' not in missing,
            'direct_earnings_provider_available':'earnings' not in missing,
            'derived_liquidity_genome_ratio':genome.get('vector',{}).get('domain_market_liquidity'),
            'liquidity_interpretation':('DIRECT_PROVIDER_MISSING__DERIVED_DASHBOARD_EVIDENCE_ONLY' if 'liquidity' in missing else 'DIRECT_PROVIDER_AVAILABLE')
        }
        try:
            # V7.4 FINAL THREE-BRAIN. Delegated so the ordering invariant lives in one
            # place: six evidence-only 4H/8H role pipelines -> cryptographic
            # pre-reconciliation freeze -> post-freeze advisory intelligence ->
            # separate 4H/8H reconciliation. Every model call still routes through this
            # class's _ask_* methods, so the V6.6.2 timeout/output-budget retry ladder
            # and the measured M4 budgets remain in force.
            run_final_three_brain(
                self, env, ledger, compact, ids, cards, regime, memory,
                source_quality or {}, runtime_policy
            )
        except Exception as e:
            env['status']='FAIL_CLOSED'; env['error']=type(e).__name__+': '+str(e); env['final']=fail_closed('V7.4 Three-Brain reasoning pipeline failed validation')
        env['runtime_events']=list(self._runtime_events)
        env=_seal_env(env)
        if write_shadow:
            row=append(self.config['shadow_ledger'],env); env['shadow_record_hash']=row['record_hash']
        return env
    def analyze(self,write_shadow=True):
        if not self._analysis_lock.acquire(blocking=False): return _seal_env({'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'status':'BUSY_FAIL_CLOSED','base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama'),'final':fail_closed('another local inference is already running; single-flight memory guard engaged')})
        try:
            snap,ledger=self.capture(); cov=coverage(snap); quality=assess_quality(snap,self.config)
            if not quality['ok']:
                env={'system':'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN','mode':'SHADOW_ONLY','generated_at_utc':utc_now(),'model':self.config['model'],'snapshot_sha256':snap.get('snapshot_sha256'),'ledger_sha256':ledger.get('ledger_sha256'),'source_coverage':cov,'source_quality':quality,'base_fia_modified':False,'forward_oos_modified':False,'paid_api_used':(False if self.provider=='ollama' else None),'hosted_api_used':(self.provider!='ollama'),'status':'FAIL_CLOSED','final':fail_closed('source quality gate failed: '+'; '.join(quality['reasons']))}
                env=_seal_env(env)
                if write_shadow:
                    row=append(self.config['shadow_ledger'],env); env['shadow_record_hash']=row['record_hash']
                return env
            out=self.analyze_ledger(ledger,source_coverage=cov,source_quality=quality,write_shadow=write_shadow,as_of_utc=snap.get('captured_at_utc')); out['snapshot_sha256']=snap.get('snapshot_sha256'); return out
        finally:self._analysis_lock.release()
