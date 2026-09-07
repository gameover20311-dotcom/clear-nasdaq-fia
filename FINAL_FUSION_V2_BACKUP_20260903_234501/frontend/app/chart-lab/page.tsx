"use client";

import { useMemo, useState } from "react";
import styles from "./chart-lab.module.css";

type Obj = Record<string, any>;

const FEATURES: [string, string][] = [
  ["htf_poi", "HTF POI"],
  ["order_block", "Order Block"],
  ["fair_value_gap", "FVG"],
  ["liquidity_sweep", "Liquidity Sweep"],
  ["smt", "SMT"],
  ["structure_shift", "CHoCH / MSS / BOS"],
  ["displacement", "Displacement"],
  ["execution_confirmation", "Execution Confirmation"],
];

function Badge({ value }: { value: string }) {
  const key = String(value || "").toUpperCase();
  const tone = key.includes("BULL") || key === "ALIGNED" ? styles.good : key.includes("BEAR") || key === "CONFLICT" || key === "NO_TRADE" ? styles.bad : styles.neutral;
  return <span className={`${styles.badge} ${tone}`}>{value || "—"}</span>;
}

export default function ChartLab() {
  const [file, setFile] = useState<File | null>(null);
  const [direction, setDirection] = useState("BULLISH");
  const [timeframe, setTimeframe] = useState("1M");
  const [reasoning, setReasoning] = useState("");
  const [vision, setVision] = useState<Obj | null>(null);
  const [result, setResult] = useState<Obj | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const confirmed = useMemo(() => result?.independent_feature_check?.confirmed_by_both || [], [result]);
  const userOnly = useMemo(() => result?.independent_feature_check?.user_only_unconfirmed || [], [result]);

  async function analyze() {
    if (!file) {
      setError("Chart image select karo.");
      return;
    }
    setBusy(true);
    setError("");
    setVision(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const vr = await fetch("/api/fia/chart-advanced", { method: "POST", body: form });
      const vp = await vr.json();
      if (!vr.ok || !vp?.ok) throw new Error(vp?.detail || vp?.error || `Vision HTTP ${vr.status}`);
      const analysis = vp.analysis;
      setVision(analysis);

      const cr = await fetch("/api/fia/three-way-confluence", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          user_analysis: { direction, timeframe, reasoning },
          vision_analysis: analysis,
        }),
      });
      const cp = await cr.json();
      if (!cr.ok || !cp?.ok) throw new Error(cp?.detail || cp?.error || `Confluence HTTP ${cr.status}`);
      setResult(cp);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return <main className={styles.shell}>
    <header className={styles.header}>
      <div>
        <div className={styles.kicker}>CLEAR NASDAQ — FIA · PHASE 31</div>
        <h1>Independent A++ Chart Intelligence</h1>
        <p>Vision پہلے chart کو FIA اور تمہاری direction دیکھے بغیر analyze کرتا ہے، پھر FIA + User + Vision تینوں کا الگ comparison ہوتا ہے۔</p>
      </div>
      <a href="/" className={styles.back}>← Dashboard</a>
    </header>

    <section className={styles.grid}>
      <div className={styles.card}>
        <div className={styles.step}>01 · YOUR CHART</div>
        <h2>Upload Analysis Screenshot</h2>
        <label className={styles.drop}>
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] || null)} />
          <strong>{file ? file.name : "CHOOSE PNG / JPG / WEBP"}</strong>
          <span>Vision FIA direction نہیں دیکھے گا۔</span>
        </label>
      </div>

      <div className={styles.card}>
        <div className={styles.step}>02 · YOUR INDEPENDENT PLAN</div>
        <h2>Tell FIA What You See</h2>
        <div className={styles.row}>
          {(["BULLISH", "BEARISH", "NEUTRAL"] as const).map(x => <button key={x} className={direction === x ? styles.active : ""} onClick={() => setDirection(x)}>{x}</button>)}
        </div>
        <select value={timeframe} onChange={e => setTimeframe(e.target.value)} className={styles.select}>
          {["1M","5M","15M","30M","1H","4H","1D"].map(x => <option key={x}>{x}</option>)}
        </select>
        <textarea value={reasoning} onChange={e => setReasoning(e.target.value)} placeholder="Example: HTF demand POI, Asia liquidity swept, 1m CHoCH + displacement..." className={styles.textarea} />
      </div>

      <div className={styles.card}>
        <div className={styles.step}>03 · RUN INDEPENDENT CHECK</div>
        <h2>Vision → Then Three-Way Confluence</h2>
        <button onClick={analyze} disabled={busy} className={styles.run}>{busy ? "ANALYZING…" : "ANALYZE WITH FIA"}</button>
        {error ? <div className={styles.error}>{error}</div> : null}
        <div className={styles.safety}>Research only · Broker execution OFF · A/A+/A++ remains OOS-validation gated.</div>
      </div>
    </section>

    {vision ? <section className={styles.card}>
      <div className={styles.step}>INDEPENDENT VISION RESULT</div>
      <div className={styles.metrics}>
        <div><span>Vision direction</span><Badge value={vision.direction} /></div>
        <div><span>Bullish</span><strong>{vision.bullish_probability}%</strong></div>
        <div><span>Bearish</span><strong>{vision.bearish_probability}%</strong></div>
        <div><span>Confidence</span><strong>{vision.confidence}%</strong></div>
      </div>
      <div className={styles.featureGrid}>
        {FEATURES.map(([key,label]) => {
          const v = key === "order_block" ? vision.order_blocks : key === "fair_value_gap" ? vision.fair_value_gaps : vision[key];
          const detected = Array.isArray(v) ? v.length > 0 : Boolean(v?.detected ?? v);
          return <div key={key} className={styles.feature}><span>{label}</span><strong>{detected ? "DETECTED" : "—"}</strong></div>;
        })}
      </div>
      <div className={styles.thesis}>{vision.thesis || "No thesis returned."}</div>
    </section> : null}

    {result ? <section className={styles.card}>
      <div className={styles.step}>FIA + USER + INDEPENDENT VISION</div>
      <div className={styles.metrics}>
        <div><span>FIA</span><Badge value={result.fia_direction} /></div>
        <div><span>You</span><Badge value={result.user_direction} /></div>
        <div><span>Vision</span><Badge value={result.vision_direction} /></div>
        <div><span>Three-way</span><Badge value={result.three_way_alignment} /></div>
        <div><span>Candidate grade</span><strong>{result.candidate_setup_grade}</strong></div>
        <div><span>Confluence score</span><strong>{result.confluence_score}</strong></div>
      </div>
      <div className={styles.twoCols}>
        <div><h3>Confirmed by you + Vision</h3>{confirmed.length ? confirmed.map((x:string) => <div className={styles.line} key={x}>✓ {x.replaceAll("_"," ")}</div>) : <div className={styles.muted}>No shared feature confirmation.</div>}</div>
        <div><h3>User claims not confirmed by Vision</h3>{userOnly.length ? userOnly.map((x:string) => <div className={styles.warn} key={x}>! {x.replaceAll("_"," ")}</div>) : <div className={styles.muted}>None.</div>}</div>
      </div>
      <div className={styles.thesis}>{result.note}</div>
    </section> : null}
  </main>;
}
