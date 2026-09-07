"use client";
import React,{useEffect,useRef,useState} from "react";
export default function Phase33(){
 const [d,setD]=useState<any>(null),[bt,setBt]=useState<any>(null),[prompt,setPrompt]=useState("Summarize current pre-move evidence"); const canvas=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{ fetch("/api/phase33/live").then(r=>r.json()).then(setD); fetch("/api/phase33/backtest").then(r=>r.json()).then(setBt); let ws:WebSocket|null=null; try{ws=new WebSocket("ws://127.0.0.1:8001/api/phase33/stream"); ws.onmessage=e=>setD((x:any)=>({...x,...JSON.parse(e.data)}));}catch{} return()=>ws?.close();},[]);
 useEffect(()=>{ const c=canvas.current;if(!c)return; const gl=c.getContext("webgl"); if(!gl)return; gl.clearColor(.03,.05,.08,1);gl.clear(gl.COLOR_BUFFER_BIT); },[d]);
 const speak=()=>{const SR=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;if(!SR)return alert("Browser speech recognition unavailable");const r=new SR();r.onresult=(e:any)=>setPrompt(e.results[0][0].transcript);r.start();};
 const ask=async()=>{const r=await fetch("http://127.0.0.1:8001/api/phase33/copilot?prompt="+encodeURIComponent(prompt)); alert(JSON.stringify(await r.json(),null,2));};
 return <main style={{minHeight:"100vh",background:"#070b11",color:"#eef4ff",padding:24,fontFamily:"system-ui"}}>
  <h1>FIA Phase 33 · Institutional Pre-Move</h1><p>Research-only · broker execution disabled</p>
  <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))",gap:12}}>
   <Card t="State" v={d?.state||"—"}/><Card t="Direction" v={d?.direction||"—"}/><Card t="Decision strength" v={d?.decision_strength_0_100??d?.strength??"—"}/><Card t="Alert" v={String(d?.alert?.fire??false)}/>
  </div>
  <section style={{marginTop:18,padding:16,border:"1px solid #223044",borderRadius:12}}><h2>WebGL Volatility Surface</h2><canvas ref={canvas} width={900} height={240} style={{width:"100%",height:240,borderRadius:8}}/><small>Renders live surface only when verified options-chain points are supplied; missing data is not fabricated.</small></section>
  <section style={{marginTop:18,padding:16,border:"1px solid #223044",borderRadius:12}}><h2>AI Copilot</h2><input value={prompt} onChange={e=>setPrompt(e.target.value)} style={{width:"70%",padding:10}}/><button onClick={speak} style={{margin:6,padding:10}}>🎙 Voice</button><button onClick={ask} style={{padding:10}}>Ask</button></section>
  <section style={{marginTop:18,padding:16,border:"1px solid #223044",borderRadius:12}}><h2>Backtest Replay Summary</h2><pre style={{whiteSpace:"pre-wrap",maxHeight:420,overflow:"auto"}}>{JSON.stringify(bt,null,2)}</pre></section>
 </main>
}
function Card({t,v}:{t:string,v:any}){return <div style={{padding:16,border:"1px solid #223044",borderRadius:12,background:"#0c131d"}}><small>{t}</small><div style={{fontSize:28,fontWeight:700}}>{String(v)}</div></div>}
