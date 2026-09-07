"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Obj = Record<string, any>;
type View = "overview" | "intelligence" | "liquidity" | "validation";

const API = "/api/fia/dashboard";

const asObj = (value: any): Obj => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const asList = (value: any): any[] => Array.isArray(value) ? value : [];
const finite = (value: any): number | null => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};
const percent = (value: any, digits = 1) => {
  const parsed = finite(value);
  return parsed === null ? "—" : `${parsed.toFixed(digits)}%`;
};
const ratio = (value: any, digits = 0) => {
  const parsed = finite(value);
  if (parsed === null) return "—";
  return `${(Math.abs(parsed) <= 1 ? parsed * 100 : parsed).toFixed(digits)}%`;
};
const number = (value: any, digits = 2) => {
  const parsed = finite(value);
  return parsed === null ? "—" : parsed.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
};
const words = (value: any) => String(value ?? "—").replace(/_/g, " ");
const isHealthy = (status: any) => ["LIVE", "OK", "PASS", "READY", "HEALTHY", "AVAILABLE"].includes(String(status ?? "").toUpperCase());
const isBad = (status: any) => ["ERROR", "FAILED", "FAIL", "UNAVAILABLE", "STALE"].includes(String(status ?? "").toUpperCase());
const toneFor = (value: any) => isHealthy(value) ? "good" : isBad(value) ? "bad" : "warn";

function Icon({ name }: { name: View | "refresh" | "shield" }) {
  const paths: Record<string, React.ReactNode> = {
    overview: <><path d="M4 4h6v6H4zM14 4h6v10h-6zM4 14h6v6H4zM14 18h6v2h-6z" /></>,
    intelligence: <><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1"/></>,
    liquidity: <><path d="M4 7h16M4 12h16M4 17h16"/><circle cx="8" cy="7" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="11" cy="17" r="2"/></>,
    validation: <><path d="m5 12 4 4L19 6"/><path d="M21 12a9 9 0 1 1-5.3-8.2"/></>,
    refresh: <><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></>,
    shield: <><path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6z"/><path d="m9 12 2 2 4-5"/></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function Badge({ value, tone }: { value: any; tone?: string }) {
  const resolved = tone || toneFor(value);
  return <span className={`badge ${resolved}`}><i />{words(value).toUpperCase()}</span>;
}

function Card({ title, kicker, children, className = "" }: { title: string; kicker?: string; children: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`}>
    <header className="cardHeader"><div>{kicker && <div className="kicker">{kicker}</div>}<h2>{title}</h2></div></header>
    {children}
  </section>;
}

function Metric({ label, value, note, tone = "" }: { label: string; value: React.ReactNode; note?: React.ReactNode; tone?: string }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}

function Empty({ children = "Data is not available from the backend." }: { children?: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

function EvidenceList({ items, tone }: { items: any[]; tone: "bull" | "bear" }) {
  if (!items.length) return <Empty>No verified {tone === "bull" ? "bullish" : "bearish"} evidence returned.</Empty>;
  return <div className="evidenceList">{items.slice(0, 5).map((item, index) => {
    const obj = asObj(item);
    const text = typeof item === "string" ? item : obj.detail || obj.name || obj.reason || "Evidence item";
    return <div className={`evidence ${tone}`} key={`${index}-${text}`}><b>{index + 1}</b><span>{text}</span></div>;
  })}</div>;
}

function StatusRail({ label, value, detail }: { label: string; value: any; detail?: string }) {
  return <div className="statusRail"><span className={`railDot ${toneFor(value)}`} /><div><b>{label}</b><small>{detail || words(value)}</small></div><Badge value={value || "UNKNOWN"} /></div>;
}

export default function Dashboard() {
  const [payload, setPayload] = useState<Obj | null>(null);
  const [view, setView] = useState<View>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [receivedAt, setReceivedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(API, { cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body?.ok !== true) throw new Error(body?.detail || body?.error || `HTTP ${response.status}`);
      setPayload(body);
      setReceivedAt(new Date());
      setError("");
    } catch (caught: any) {
      setPayload(null);
      setError(caught?.message || "Backend unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const live = asObj(payload?.live);
  const snapshot = asObj(live.snapshot);
  const data = asObj(snapshot.data && typeof snapshot.data === "object" ? snapshot.data : snapshot);
  const forecast = asObj(live.forecast);
  const cognitive = asObj(live.cognitive);
  const critic = asObj(cognitive.critic);
  const hypotheses = asObj(cognitive.hypotheses);
  const analogy = asObj(cognitive.historical_analogy);
  const fusion = asObj(cognitive.fusion);
  const contributions = asList(fusion.contributions);
  const backtest = asObj(payload?.backtest);
  const quality = asObj(backtest.data_quality);
  const authenticity = asObj(backtest.authenticity);
  const provider = asObj(data.provider_health);
  const sourceHealth = asObj(data.source_health);
  const mega = asObj(data.mega_cap_details);
  const liquidityGroups = asObj(live.liquidity_groups);
  const liquidity = asObj(live.liquidity);
  const earnings = asObj(live.upcoming_earnings);

  const rawDirection = String(forecast.direction || "UNKNOWN").toUpperCase();
  const bullProbability = finite(forecast.bullish_probability);
  const bearProbability = finite(forecast.bearish_probability);
  const directional = ["BULLISH", "BEARISH"].includes(rawDirection) && bullProbability !== null && bearProbability !== null && Math.abs(bullProbability - bearProbability) >= 0.1;
  const direction = directional ? rawDirection : "NO EDGE";
  const directionTone = direction === "BULLISH" ? "bull" : direction === "BEARISH" ? "bear" : "neutral";
  const forecastStatus = String(forecast.status || (error ? "UNAVAILABLE" : "UNKNOWN")).toUpperCase();
  const backendTone = error || isBad(forecastStatus) ? "bad" : forecastStatus === "LIVE" ? "good" : "warn";
  const generatedAt = payload?.generated_at || forecast.generated_at || data.timestamp;

  const signals = useMemo(() => asList(forecast.signals).slice().sort((a, b) => Math.abs(finite(b?.score) || 0) - Math.abs(finite(a?.score) || 0)), [forecast.signals]);
  const bullishEvidence = asList(forecast.bullish_evidence);
  const bearishEvidence = asList(forecast.bearish_evidence);
  const objections = asList(critic.objections);
  const dominant = hypotheses.dominant_hypothesis || cognitive.dominant_hypothesis;

  const accuracy4 = asObj(backtest.accuracy_4h);
  const accuracy8 = asObj(backtest.accuracy_8h);
  const brier4 = asObj(backtest.brier_4h);
  const brier8 = asObj(backtest.brier_8h);
  const contracts = asObj(quality.liquidity_contracts);
  const months = asList(backtest.monthly);

  const whole = asObj(payload?.whole_system_backtest);
  const wholeHorizons = asObj(whole.horizons);
  const whole4 = asObj(wholeHorizons["4h"]);
  const whole8 = asObj(wholeHorizons["8h"]);
  const wholeProgress = asObj(whole.progress);
  const factorImportance = asObj(whole.factor_importance);
  const rankedFactors = asList(factorImportance.ranked_groups);
  const liveDual = asObj(whole.live_forward_oos);
  const live4 = asObj(liveDual["4h"]);
  const live8 = asObj(liveDual["8h"]);
  const live4Windows = asObj(live4.windows);
  const live8Windows = asObj(live8.windows);
  const phase25 = asObj(payload?.phase25);
  const brain66 = asObj(payload?.brain_v66);
  const brainOllama = asObj(brain66.ollama);
  const brainShadow = asObj(brain66.latest_shadow);
  const backendRegistry = asList(payload?.backend_registry);

  const modules = [
    ["Provider network", provider.overall || snapshot.status || "UNKNOWN", `${finite(provider.score) !== null ? percent(provider.score) + " health" : "Source health from live snapshot"}`],
    ["Forecast fusion", forecastStatus, `${signals.length} active evidence signals`],
    ["Cognitive critic", cognitive.status || (cognitive.ok === false ? "UNAVAILABLE" : cognitive.reliability || "UNKNOWN"), `${objections.length} objections returned`],
    ["NQ structure", finite(data.nq_structure) !== null ? "AVAILABLE" : "UNKNOWN", `Score ${number(data.nq_structure, 3)}`],
    ["Macro & rates", data.macro_status || (finite(data.macro) !== null ? "AVAILABLE" : "UNKNOWN"), `DXY ${number(data.dxy_value, 2)} · US10Y ${number(data.us10y_value, 3)}`],
    ["Leadership & breadth", Object.keys(mega).length ? "AVAILABLE" : "UNKNOWN", `${Object.keys(mega).length} tracked leaders`],
    ["Liquidity map", Object.keys(liquidityGroups).length || Object.keys(liquidity).length ? "AVAILABLE" : "UNKNOWN", `${Object.keys(liquidityGroups).length} instrument groups`],
    ["News intelligence", data.news_status || (finite(data.news_articles) !== null ? "AVAILABLE" : "UNKNOWN"), `${finite(data.news_articles) ?? 0} articles observed`],
    ["Earnings calendar", earnings.available === true ? "AVAILABLE" : "UNKNOWN", `${asList(earnings.events).length} tracked events`],
    ["V6.6 GPT-OSS Brain", brain66.status || "UNKNOWN", `${brain66.model || "gpt-oss:20b"} · Ollama ${brainOllama.status || "UNKNOWN"}`],
    ["Phase 25 chart confluence", phase25.status || "AWAITING_CHART", phase25.latest_grade ? `Latest ${phase25.latest_grade}` : "No verified chart assessment yet"],
    ["Whole-system 1Y replay", whole.final ? "PASS" : whole.state || "NOT_RUN", `${wholeProgress.completed_cases ?? 0}/${wholeProgress.total_cases ?? 0} dual-resolved cases`],
    ["Forward-OOS 4H", live4.status || "COLLECTING", `${asObj(live4Windows.all_resolved).directional_resolved_calls ?? 0} resolved directional calls`],
    ["Forward-OOS 8H", live8.status || "COLLECTING", `${asObj(live8Windows.all_resolved).directional_resolved_calls ?? 0} resolved directional calls`],
    ["Historical diagnostics", backtest.available === true ? "AVAILABLE" : "UNKNOWN", `${finite(backtest.forecasts) ?? 0} legacy replay checkpoints`],
  ] as const;

  return <div className="appFrame">
    <aside className="sideNav">
      <div className="brand">
        <div className="brandMark">F</div>
        <div><b>CLEAR NASDAQ</b><span>FIA RESEARCH OS</span></div>
      </div>
      <nav aria-label="Dashboard views">
        {(["overview", "intelligence", "liquidity", "validation"] as View[]).map((item) => <button key={item} className={view === item ? "active" : ""} onClick={() => setView(item)}><Icon name={item} /><span>{item}</span></button>)}
      </nav>
      <div className="guardrail"><Icon name="shield"/><div><b>Research only</b><span>Broker execution is off</span></div></div>
    </aside>

    <main className="workspace">
      <header className="topbar">
        <div><div className="kicker">NASDAQ-100 · 4–8H RESEARCH WINDOW</div><h1>Market Intelligence Cockpit</h1></div>
        <div className="topActions">
          <div className={`connection ${backendTone}`}><i/><div><b>{error ? "BACKEND UNAVAILABLE" : forecastStatus}</b><span>{receivedAt ? `Received ${receivedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Waiting for atomic snapshot"}</span></div></div>
          <button className="refresh" onClick={load} disabled={loading}><Icon name="refresh"/><span>{loading ? "Loading" : "Refresh"}</span></button>
        </div>
      </header>

      {error && <div className="errorState"><strong>FIA cannot verify live data.</strong><span>{error}. The dashboard has cleared the old snapshot instead of showing stale certainty.</span></div>}
      {!payload && !error && <div className="loadingState"><i/><span>Building one atomic research snapshot…</span></div>}

      {payload && view === "overview" && <>
        <section className="heroGrid">
          <div className={`outlookCard ${directionTone}`}>
            <div className="outlookTop"><div><div className="kicker">CURRENT RESEARCH OUTLOOK</div><div className="direction">{direction}</div></div><Badge value={forecastStatus}/></div>
            <div className="probabilityLabels"><span>Bullish <b>{percent(bullProbability)}</b></span><span>Bearish <b>{percent(bearProbability)}</b></span></div>
            <div className="probabilityTrack" aria-label="Bullish versus bearish probability"><div className="bullFill" style={{ width: `${Math.max(0, Math.min(100, bullProbability ?? 50))}%` }}/></div>
            <div className="outlookFoot"><span>{forecast.symbol || "NQ"} · next {forecast.horizon_hours || "4–8"} hours</span><span>{words(forecast.probability_status || "uncalibrated research score")}</span></div>
          </div>
          <div className="heroMetrics">
            <Metric label="Evidence reliability" value={percent(forecast.confidence)} note={words(forecast.confidence_status || "Not a win-rate")}/>
            <Metric label="Market regime" value={words(forecast.regime)} note={`Model score ${number(forecast.score, 3)}`}/>
            <Metric label="Data coverage" value={ratio(forecast.data_coverage)} note="Available live inputs"/>
            <Metric label="Intelligence coverage" value={ratio(forecast.intelligence_coverage)} note="Usable specialist evidence"/>
          </div>
        </section>

        <section className="overviewGrid">
          <Card title="What supports the outlook" kicker="EVIDENCE, NOT CERTAINTY" className="span2">
            <div className="evidenceColumns"><div><h3>Bullish case</h3><EvidenceList items={bullishEvidence} tone="bull"/></div><div><h3>Bearish case</h3><EvidenceList items={bearishEvidence} tone="bear"/></div></div>
          </Card>
          <Card title="Thesis guardrail" kicker="WHAT WOULD INVALIDATE IT">
            <div className="thesis">{forecast.thesis || "No verified thesis returned."}</div>
            <div className="invalidation">{asList(forecast.invalidation).length ? asList(forecast.invalidation).slice(0, 4).map((item, index) => <div key={index}><b>{index + 1}</b><span>{String(item)}</span></div>) : <Empty>No invalidation rules returned.</Empty>}</div>
          </Card>
          <Card title="Your Chart + FIA" kicker="PHASE 25 · REAL CONFLUENCE ONLY" className="span3">
            <div className="metricStrip">
              <Metric label="Status" value={words(phase25.status || "AWAITING_CHART")}/>
              <Metric label="Latest grade" value={phase25.latest_grade || "—"}/>
              <Metric label="Confluence score" value={phase25.confluence_score ?? "—"}/>
              <Metric label="Alignment" value={phase25.alignment_pct == null ? "—" : `${phase25.alignment_pct}%`}/>
              <Metric label="Completeness" value={phase25.completeness_pct == null ? "—" : `${phase25.completeness_pct}%`}/>
              <Metric label="Research alert" value={words(phase25.research_alert || "NONE")}/>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"center",marginTop:14,flexWrap:"wrap"}}>
              <span className="note">{phase25.note || "A real chart assessment appears here only after the chart confluence pipeline records it."}</span>
              <a href="/chart-lab" style={{fontWeight:800,textDecoration:"underline"}}>OPEN CHART LAB →</a>
            </div>
          </Card>
          <Card title="System truth map" kicker="ACTIVE BACKEND OUTPUTS" className="span3">
            <div className="moduleGrid">{modules.map(([label, status, detail]) => <StatusRail key={label} label={label} value={status} detail={detail}/>)}</div>
          </Card>
        </section>
      </>}

      {payload && view === "intelligence" && <>
        <section className="pageIntro"><div><div className="kicker">SPECIALIST BRAINS + INDEPENDENT CRITIC</div><h2>Intelligence evidence</h2></div><Badge value={cognitive.status || cognitive.reliability || "UNKNOWN"}/></section>
        <section className="intelligenceGrid">
          <Card title="Cognitive synthesis" kicker="MULTI-HYPOTHESIS REVIEW" className="span2">
            <div className="cognitiveHero"><Metric label="Cognitive direction" value={words(cognitive.direction)}/><Metric label="Raw bullish" value={percent(cognitive.raw_probability_before_calibration ?? cognitive.bullish_probability)}/><Metric label="Reliability" value={ratio(cognitive.reliability_score)} note={words(cognitive.reliability)}/><Metric label="Decision gate" value={words(cognitive.decision_gate)}/></div>
            <div className="hypothesis"><span>Dominant hypothesis</span><strong>{dominant || "No dominant hypothesis returned."}</strong></div>
          </Card>
          <Card title="Independent critic" kicker="COUNTER-EVIDENCE">
            <div className="criticHead"><Badge value={critic.severity || "UNKNOWN"}/><span>{objections.length} objections</span></div>
            <div className="objections">{objections.length ? objections.slice(0, 6).map((item, index) => <div key={index}>{String(item)}</div>) : <Empty>No critic objections returned.</Empty>}</div>
          </Card>
          <Card title="Specialist contribution" kicker="INDEPENDENCE + WEIGHT" className="span2">
            <div className="signalTable"><div className="tableHead"><span>Specialist</span><span>Contribution</span><span>Weight</span><span>Reliability</span></div>{contributions.length ? contributions.slice(0, 12).map((item, index) => {
              const score = finite(item.contribution) || 0;
              return <div className="tableRow" key={index}><b>{words(item.specialist)}</b><span className={score > 0 ? "positive" : score < 0 ? "negative" : "muted"}>{score > 0 ? "+" : ""}{number(score, 3)}</span><span>{number(item.weight, 3)}</span><span>{ratio(item.reliability)}</span></div>;
            }) : <Empty>No specialist contribution ledger returned.</Empty>}</div>
          </Card>
          <Card title="Signal engine" kicker="STRONGEST FIRST">
            <div className="signalStack">{signals.length ? signals.slice(0, 10).map((item, index) => {
              const score = finite(item.score) || 0;
              return <div className="signalLine" key={index}><div><b>{item.name || `Signal ${index + 1}`}</b><span>{item.detail || words(item.freshness)}</span></div><strong className={score > 0 ? "positive" : score < 0 ? "negative" : "muted"}>{score > 0 ? "+" : ""}{number(score, 3)}</strong></div>;
            }) : <Empty/>}</div>
          </Card>
          <Card title="V6.6 causal-twin brain" kicker="GPT-OSS 20B · LOCAL RUNTIME" className="span3">
            <div className="metricStrip">
              <Metric label="Brain status" value={words(brain66.status || "UNKNOWN")}/>
              <Metric label="Model" value={brain66.model || "gpt-oss:20b"}/>
              <Metric label="Version" value={brain66.version || "—"}/>
              <Metric label="Ollama" value={words(brainOllama.status || "UNKNOWN")}/>
              <Metric label="Latest shadow" value={words(brainShadow.status || "—")}/>
              <Metric label="Shadow confidence" value={brainShadow.confidence == null ? "—" : `${brainShadow.confidence}%`}/>
            </div>
            <p className="note">{brain66.truth_note || "Runtime health is not a performance claim."}</p>
          </Card>
          <Card title="Historical analogy" kicker="CONTEXT, NOT AUTHORITY" className="span3">
            <div className="metricStrip"><Metric label="Available" value={analogy.available === true ? "YES" : "NO"}/><Metric label="Sample" value={analogy.sample_size ?? "—"}/><Metric label="Similarity" value={number(analogy.mean_similarity, 2)}/><Metric label="Status" value={words(analogy.status || analogy.reason)}/></div>
          </Card>
        </section>
      </>}

      {payload && view === "liquidity" && <>
        <section className="pageIntro"><div><div className="kicker">LEVELS + MARKET CONTEXT</div><h2>Liquidity and cross-market map</h2></div><Badge value={Object.keys(liquidityGroups).length ? "AVAILABLE" : "UNKNOWN"}/></section>
        <section className="marketStrip">
          <Metric label="NQ structure" value={number(data.nq_structure, 3)} note={words(sourceHealth.nq?.freshness)}/>
          <Metric label="SPX confirmation" value={number(data.spx_confirmation, 3)} note={words(sourceHealth.spx?.freshness)}/>
          <Metric label="DXY" value={number(data.dxy_value, 2)} note={data.dxy_source || "Source unverified"}/>
          <Metric label="US10Y" value={number(data.us10y_value, 3)} note={data.us10y_source || "Source unverified"}/>
          <Metric label="Semiconductors" value={number(data.semis, 3)}/>
          <Metric label="Breadth" value={number(data.breadth, 3)}/>
        </section>
        <section className="liquidityLayout">
          <Card title="Liquidity levels" kicker="BACKEND-VERIFIED PRICE MAP" className="span2">
            <div className="levelGroups">{Object.keys(liquidityGroups).length ? Object.entries(liquidityGroups).map(([groupName, raw]) => {
              const group = asObj(raw); const levels = asObj(group.levels);
              return <div className="levelGroup" key={groupName}><div className="levelGroupHead"><div><b>{words(group.instrument || groupName).toUpperCase()}</b><span>Reference {number(group.current_price, 2)}</span></div><span>{Object.keys(levels).length} levels</span></div><div className="levels">{Object.entries(levels).map(([key, rawLevel]) => {
                const level = asObj(rawLevel);
                return <div className="level" key={key}><div><b>{level.name || words(key)}</b><span>{words(level.timeframe || level.status)}</span></div><strong>{number(level.price, 2)}</strong><Badge value={level.status || "UNKNOWN"}/></div>;
              })}</div></div>;
            }) : Object.keys(liquidity).length ? <div className="levels">{Object.entries(liquidity).map(([key, raw]) => { const level = asObj(raw); return <div className="level" key={key}><div><b>{level.name || words(key)}</b><span>{words(level.timeframe || level.side)}</span></div><strong>{number(level.price, 2)}</strong><Badge value={level.status || "UNKNOWN"}/></div>; })}</div> : <Empty/>}</div>
          </Card>
          <Card title="Mega-cap leadership" kicker="INDEX IMPACT">
            <div className="tickerGrid">{Object.keys(mega).length ? Object.entries(mega).map(([symbol, raw]) => {
              const item = asObj(raw); const change = finite(item.change_percent);
              return <div className="ticker" key={symbol}><div><b>{symbol}</b><span>{words(item.signal)}</span></div><strong className={(change || 0) > 0 ? "positive" : (change || 0) < 0 ? "negative" : "muted"}>{percent(change)}</strong></div>;
            }) : <Empty/>}</div>
          </Card>
          <Card title="Upcoming earnings" kicker="NEXT VERIFIED EVENTS">
            <div className="eventList">{asList(earnings.events).length ? asList(earnings.events).slice(0, 10).map((event, index) => <div className="event" key={index}><div><b>{event.symbol || "—"}</b><span>{event.date || event.datetime || "Date unavailable"}</span></div><strong>{event.hour || "—"}</strong></div>) : <Empty>No tracked earnings returned for the current window.</Empty>}</div>
          </Card>
        </section>
      </>}

      {payload && view === "validation" && <>
        <section className="pageIntro"><div><div className="kicker">PROVENANCE BEFORE PERFORMANCE</div><h2>Validation and data truth</h2></div><Badge value={authenticity.status || "UNPROVEN"}/></section>
        <div className="truthBanner"><Icon name="shield"/><div><b>Historical results are revealed diagnostics.</b><span>They are not untouched forward-OOS proof and they do not guarantee future performance.</span></div></div>
        <section className="validationGrid">
          <Card title="FINAL whole-system replay" kicker="ACTUAL V6.6 BRAIN · ONE LOCKED FORECAST · GENUINE 4H + 8H RESOLUTION" className="span2">
            <div className="metricStrip">
              <Metric label="Truth state" value={whole.final ? "FINAL" : words(whole.state || "NOT RUN")}/>
              <Metric label="Progress" value={`${wholeProgress.completed_cases ?? 0}/${wholeProgress.total_cases ?? 0}`} note={wholeProgress.pct == null ? "—" : `${wholeProgress.pct}%`}/>
              <Metric label="4H win rate" value={whole4.win_rate == null ? "—" : `${whole4.win_rate}%`} note={`W ${whole4.wins ?? 0} · L ${whole4.losses ?? 0}`}/>
              <Metric label="8H win rate" value={whole8.win_rate == null ? "—" : `${whole8.win_rate}%`} note={`W ${whole8.wins ?? 0} · L ${whole8.losses ?? 0}`}/>
              <Metric label="4H coverage" value={whole4.directional_coverage_pct == null ? "—" : `${whole4.directional_coverage_pct}%`} note={`NO_EDGE ${whole4.no_edge ?? 0} · FAIL ${whole4.fail_closed ?? 0}`}/>
              <Metric label="8H coverage" value={whole8.directional_coverage_pct == null ? "—" : `${whole8.directional_coverage_pct}%`} note={`NO_EDGE ${whole8.no_edge ?? 0} · FAIL ${whole8.fail_closed ?? 0}`}/>
              <Metric label="4H Brier" value={whole4.brier ?? "—"} note={`n=${whole4.brier_n ?? 0}`}/>
              <Metric label="8H Brier" value={whole8.brier ?? "—"} note={`n=${whole8.brier_n ?? 0}`}/>
            </div>
            <p className="note">4H is the genuine early market resolution of the same locked V6.6 whole-system 4–8H research forecast. It is not falsely labelled as a separate second Brain run. Win rate never hides NO_EDGE, FAIL_CLOSED or unresolved cases.</p>
          </Card>
          <Card title="Live Forward-OOS" kicker="UNSEEN RESULTS · HISTORICAL NEVER MIXED">
            <div className="kvList">
              <div><span>4H current week</span><b>{asObj(live4Windows.current_week).win_rate == null ? "Collecting" : `${asObj(live4Windows.current_week).win_rate}%`}</b></div>
              <div><span>8H current week</span><b>{asObj(live8Windows.current_week).win_rate == null ? "Collecting" : `${asObj(live8Windows.current_week).win_rate}%`}</b></div>
              <div><span>4H previous week</span><b>{asObj(live4Windows.previous_week).win_rate == null ? "Collecting" : `${asObj(live4Windows.previous_week).win_rate}%`}</b></div>
              <div><span>8H previous week</span><b>{asObj(live8Windows.previous_week).win_rate == null ? "Collecting" : `${asObj(live8Windows.previous_week).win_rate}%`}</b></div>
              <div><span>4H last 30d</span><b>{asObj(live4Windows.last_30d).win_rate == null ? "Collecting" : `${asObj(live4Windows.last_30d).win_rate}%`}</b></div>
              <div><span>8H last 30d</span><b>{asObj(live8Windows.last_30d).win_rate == null ? "Collecting" : `${asObj(live8Windows.last_30d).win_rate}%`}</b></div>
            </div>
          </Card>
          <Card title="Factor importance" kicker="PHASE 36 DIAGNOSTIC · NOT CAUSAL PROOF">
            <div className="signalStack">{rankedFactors.length ? rankedFactors.slice(0, 10).map((item, index) => <div className="signalLine" key={index}><div><b>{words(item.label || item.group)}</b><span>{words(item.claim_scope)}</span></div><strong>{number(item.diagnostic_score, 2)}</strong></div>) : <Empty>No factor ranking available yet.</Empty>}</div>
          </Card>
          <Card title="Backend route registry" kicker="REGISTERED ROUTES · NOT FAKE LIVE CLAIMS" className="span2">
            <div className="monthlyTable"><div className="tableHead"><span>Route</span><span>Method</span><span>Status</span><span>Meaning</span></div>{backendRegistry.length ? backendRegistry.map((route, index) => <div className="tableRow" key={`${route.path}-${index}`}><b>{route.path}</b><span>{asList(route.methods).join(", ") || "—"}</span><span>{route.status || "REGISTERED"}</span><span>Backend route registered</span></div>) : <Empty>No backend registry returned.</Empty>}</div>
          </Card>
        </section>
        <section className="validationMetrics">
          <Metric label="Replay checkpoints" value={backtest.forecasts ?? "—"} note={words(backtest.phase)}/>
          <Metric label="4H diagnostic accuracy" value={percent(accuracy4.accuracy, 2)} note={`n=${accuracy4.resolved ?? 0}`}/>
          <Metric label="8H diagnostic accuracy" value={percent(accuracy8.accuracy, 2)} note={`n=${accuracy8.resolved ?? 0}`}/>
          <Metric label="4H Brier" value={number(brier4.brier, 4)} note={`n=${brier4.n ?? 0}`}/>
          <Metric label="8H Brier" value={number(brier8.brier, 4)} note={`n=${brier8.n ?? 0}`}/>
          <Metric label="Market-grade claim" value={authenticity.official_market_grade_claim_eligible ? "ELIGIBLE" : "WITHHELD"} note={words(authenticity.outcome_source || "provenance unknown")}/>
        </section>
        <section className="validationGrid">
          <Card title="Data provenance" kicker="WHAT THE TEST ACTUALLY USED">
            <div className="kvList"><div><span>Result status</span><b>{words(authenticity.status)}</b></div><div><span>Future EPS used</span><b>{quality.future_eps_used ?? "—"}</b></div><div><span>Outcome source</span><b>{words(authenticity.outcome_source)}</b></div><div><span>Digest preserved</span><b>{authenticity.prediction_digest_preserved === true ? "YES" : authenticity.prediction_digest_preserved === false ? "NO" : "UNPROVEN"}</b></div></div>
            <p className="note">{authenticity.note || "No provenance note returned."}</p>
          </Card>
          <Card title="Futures contract coverage" kicker="HISTORICAL CHAIN">
            <div className="contractList">{Object.keys(contracts).length ? Object.entries(contracts).map(([name, value]) => <div key={name}><b>{name}</b><span>{String(value)} checkpoints</span></div>) : <Empty>No contract audit returned.</Empty>}</div>
          </Card>
          <Card title="Monthly robustness" kicker="DIAGNOSTIC BREAKDOWN" className="span2">
            <div className="monthlyTable"><div className="tableHead"><span>Month</span><span>Forecasts</span><span>4H accuracy</span><span>8H accuracy</span></div>{months.length ? months.map((month, index) => <div className="tableRow" key={index}><b>{month.month || month.period || "—"}</b><span>{month.forecasts ?? month.count ?? "—"}</span><span>{percent(month.accuracy_4h, 2)}</span><span>{percent(month.accuracy_8h, 2)}</span></div>) : <Empty/>}</div>
          </Card>
        </section>
      </>}

      <footer><span>Atomic snapshot: {generatedAt ? new Date(generatedAt).toLocaleString() : "—"}</span><span>FIA Research OS · Broker execution OFF</span></footer>
    </main>
  </div>;
}
