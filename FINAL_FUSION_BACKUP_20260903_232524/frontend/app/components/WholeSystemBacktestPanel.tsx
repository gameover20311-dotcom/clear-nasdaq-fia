"use client";
import { useEffect, useState } from "react";

type AnyObj = Record<string, any>;

function Metric({label,value,sub}:{label:string,value:any,sub?:string}){
  return <div style={{padding:"14px 16px",border:"1px solid rgba(148,163,184,.18)",borderRadius:14,background:"rgba(15,23,42,.54)"}}>
    <div style={{fontSize:11,letterSpacing:".08em",opacity:.62,textTransform:"uppercase"}}>{label}</div>
    <div style={{fontSize:28,fontWeight:750,lineHeight:1.2,marginTop:4}}>{value ?? "—"}</div>
    {sub ? <div style={{fontSize:11,opacity:.58,marginTop:4}}>{sub}</div> : null}
  </div>
}

export default function WholeSystemBacktestPanel(){
  const [d,setD]=useState<AnyObj|null>(null);
  useEffect(()=>{
    let alive=true;
    const load=()=>fetch("/api/fia/whole-system-backtest",{cache:"no-store"}).then(r=>r.json()).then(x=>{if(alive)setD(x)}).catch(()=>{});
    load(); const id=setInterval(load,30000); return()=>{alive=false;clearInterval(id)};
  },[]);
  const h=d?.historical_1y_whole_system;
  const progress=d?.progress;
  const live=d?.live_forward_oos?.windows;
  const isFinal=Boolean(d?.final);
  const wr=h?.win_rate;
  return <section style={{margin:"0 0 20px",padding:18,border:"1px solid rgba(148,163,184,.22)",borderRadius:18,background:"linear-gradient(180deg,rgba(2,6,23,.78),rgba(15,23,42,.56))"}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,flexWrap:"wrap",marginBottom:14}}>
      <div><div style={{fontSize:11,opacity:.58,letterSpacing:".12em"}}>RETROSPECTIVE 1Y · WHOLE CURRENT SYSTEM · PRIMARY 8H</div>
      <div style={{fontSize:20,fontWeight:750}}>CLEAR NASDAQ — Genuine Whole-System Win/Loss Proof</div></div>
      <div style={{padding:"6px 10px",borderRadius:999,border:"1px solid rgba(148,163,184,.25)",fontSize:12,fontWeight:700}}>{isFinal?"FINAL":"RUNNING"} {progress?`· ${progress.pct ?? 0}%`:""}</div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(135px,1fr))",gap:10}}>
      <Metric label="Win rate" value={wr==null?"—":`${wr}%`} sub={isFinal?`FINAL · n=${h?.win_rate_denominator ?? 0}`:"Partial result — not final"}/>
      <Metric label="Wins" value={h?.wins ?? 0}/><Metric label="Losses" value={h?.losses ?? 0}/>
      <Metric label="No edge" value={h?.no_edge ?? 0}/><Metric label="Fail closed" value={h?.fail_closed ?? 0}/>
      <Metric label="Coverage" value={h?.directional_coverage_pct==null?"—":`${h.directional_coverage_pct}%`} sub="Directional calls / eligible outcomes"/>
      <Metric label="Brier" value={h?.brier ?? "—"} sub={`n=${h?.brier_n ?? 0}`}/>
    </div>
    <div style={{marginTop:14,display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10}}>
      <Metric label="Current week" value={live?.current_week?.win_rate==null?"Collecting":`${live.current_week.win_rate}%`} sub={`W ${live?.current_week?.wins ?? 0} · L ${live?.current_week?.losses ?? 0}`}/>
      <Metric label="Previous week" value={live?.previous_week?.win_rate==null?"Collecting":`${live.previous_week.win_rate}%`} sub={`W ${live?.previous_week?.wins ?? 0} · L ${live?.previous_week?.losses ?? 0}`}/>
      <Metric label="Live last 7d" value={live?.last_7d?.win_rate==null?"Collecting":`${live.last_7d.win_rate}%`} sub={`W ${live?.last_7d?.wins ?? 0} · L ${live?.last_7d?.losses ?? 0}`}/>
      <Metric label="Live last 30d" value={live?.last_30d?.win_rate==null?"Collecting":`${live.last_30d.win_rate}%`} sub={`W ${live?.last_30d?.wins ?? 0} · L ${live?.last_30d?.losses ?? 0}`}/>
    </div>
    <div style={{fontSize:11,opacity:.55,marginTop:12}}>Retrospective 1Y and genuinely unseen Live Forward-OOS are separate. NO_EDGE / FAIL_CLOSED / unresolved are never hidden to inflate win rate. Live metrics use only the model that was actually locked pre-move in the immutable Forward-OOS ledger; they are never relabeled V6.6 after the outcome. <a href="/whole-system-backtest" style={{textDecoration:"underline"}}>Full report</a></div>
  </section>
}
