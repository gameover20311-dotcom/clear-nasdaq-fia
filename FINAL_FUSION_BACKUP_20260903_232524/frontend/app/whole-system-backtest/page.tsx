"use client";
import { useEffect, useState } from "react";
export default function WholeSystemBacktestPage(){
 const [d,setD]=useState<any>(null);
 useEffect(()=>{const f=()=>fetch("/api/fia/whole-system-backtest",{cache:"no-store"}).then(r=>r.json()).then(setD).catch(()=>{});f();const i=setInterval(f,30000);return()=>clearInterval(i)},[]);
 if(!d)return <main style={{padding:28,color:"#e2e8f0",background:"#020617",minHeight:"100vh"}}>Loading final backtest…</main>;
 const h=d?.historical_1y_whole_system||{};
 const ranked=d?.factor_importance?.ranked_groups||[];
 return <main style={{padding:28,color:"#e2e8f0",background:"#020617",minHeight:"100vh",fontFamily:"ui-sans-serif,system-ui"}}>
  <div style={{maxWidth:1200,margin:"0 auto"}}><a href="/" style={{color:"#94a3b8"}}>← Dashboard</a><h1>CLEAR NASDAQ — Whole-System Validation</h1>
  <p style={{color:"#94a3b8"}}>State: <b>{d.state}</b> · Progress: {d?.progress?.pct ?? 0}% · Primary horizon: {d.primary_horizon_hours}H</p>
  <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:12}}>{[
   ["WIN RATE",h.win_rate==null?"—":h.win_rate+"%"],["WINS",h.wins],["LOSSES",h.losses],["NO EDGE",h.no_edge],["FAIL CLOSED",h.fail_closed],["COVERAGE",h.directional_coverage_pct==null?"—":h.directional_coverage_pct+"%"],["BRIER",h.brier]
  ].map(([a,b])=><div key={String(a)} style={{padding:16,border:"1px solid #1e293b",borderRadius:14,background:"#0f172a"}}><small style={{color:"#94a3b8"}}>{a}</small><div style={{fontSize:30,fontWeight:800}}>{b ?? 0}</div></div>)}</div>
  <h2 style={{marginTop:28}}>Weekly retrospective 1Y</h2><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr>{["Period","Wins","Losses","No edge","Fail closed","Win rate"].map(x=><th key={x} style={{textAlign:"left",padding:8,borderBottom:"1px solid #334155"}}>{x}</th>)}</tr></thead><tbody>{(h.weekly||[]).map((r:any)=><tr key={r.period}><td style={{padding:8}}>{r.period}</td><td>{r.wins}</td><td>{r.losses}</td><td>{r.no_edge}</td><td>{r.fail_closed}</td><td>{r.win_rate==null?"—":r.win_rate+"%"}</td></tr>)}</tbody></table></div>
  <h2 style={{marginTop:28}}>Truth policy</h2><pre style={{whiteSpace:"pre-wrap",background:"#0f172a",padding:16,borderRadius:12,overflow:"auto"}}>{JSON.stringify(d.truth_policy,null,2)}</pre>
  <h2>Factor importance · Phase36 development-only ablation</h2>
  <p style={{color:"#94a3b8"}}>Diagnostic ranking only — not live causal proof. Missing historical institutional feeds are never fabricated.</p>
  <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr>{["Rank","Group","Label","Diagnostic score","Add accuracy pp","Remove accuracy pp"].map(x=><th key={x} style={{textAlign:"left",padding:8,borderBottom:"1px solid #334155"}}>{x}</th>)}</tr></thead><tbody>{ranked.map((r:any,i:number)=><tr key={r.group}><td style={{padding:8}}>{i+1}</td><td>{r.group}</td><td>{r.label||"—"}</td><td>{r.diagnostic_score}</td><td>{r.mean_add_accuracy_pp ?? "—"}</td><td>{r.mean_remove_accuracy_pp ?? "—"}</td></tr>)}</tbody></table></div>
  <details style={{marginTop:12}}><summary style={{cursor:"pointer",color:"#94a3b8"}}>Raw factor-importance evidence</summary><pre style={{whiteSpace:"pre-wrap",background:"#0f172a",padding:16,borderRadius:12,overflow:"auto",maxHeight:500}}>{JSON.stringify(d.factor_importance,null,2)}</pre></details>
  <h2>Live Forward-OOS</h2><pre style={{whiteSpace:"pre-wrap",background:"#0f172a",padding:16,borderRadius:12,overflow:"auto",maxHeight:500}}>{JSON.stringify(d.live_forward_oos,null,2)}</pre>
  </div></main>
}
