"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Signal = {
  name: string;
  score: number;
  weight: number;
  detail: string;
  freshness?: string;
};

type Forecast = {
  symbol: string;
  horizon_hours: number;
  direction: string;
  bullish_probability: number;
  bearish_probability: number;
  confidence: number;
  regime: string;
  status: string;
  score: number;
  signals: Signal[];
  invalidation: string[];
  generated_at: string;
  data_coverage: number;
  source_status?: Record<string, string>;
  thesis: string;
  bullish_evidence?: string[];
  bearish_evidence?: string[];
  intelligence_coverage?: number;
};

type LiquidityLevel = {
  name: string;
  timeframe: string;
  price: number | null;
  status: string;
  side: string;
  distance_pct: number | null;
  detail?: string;
};

type UserAnalysis = {
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  timeframe: string;
  notes: string;
  fileName: string;
  imageUrl: string;
};

type LiquidityResponse = {
  status: string;
  provider?: string;
  timestamp?: number;
  levels?: Record<string, LiquidityLevel>;
};

const liquidityKeys = [
  "monthly_high", "monthly_low",
  "weekly_high", "weekly_low",
  "daily_high", "daily_low",
  "asia_high", "asia_low",
  "london_high", "london_low",
  "new_york_high", "new_york_low",
];

const labelMap: Record<string, string> = {
  monthly_high: "Monthly High",
  monthly_low: "Monthly Low",
  weekly_high: "Weekly High",
  weekly_low: "Weekly Low",
  daily_high: "Daily High",
  daily_low: "Daily Low",
  asia_high: "Asia High",
  asia_low: "Asia Low",
  london_high: "London High",
  london_low: "London Low",
  new_york_high: "New York High",
  new_york_low: "New York Low",
};

function pct(value: number | undefined, digits = 1) {
  return `${Number(value ?? 0).toFixed(digits)}%`;
}

function score(value: number | undefined) {
  const n = Number(value ?? 0);
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
}

function signalTone(value: number) {
  if (value > 0.08) return "bull";
  if (value < -0.08) return "bear";
  return "neutral";
}

function freshnessTone(value?: string) {
  return value === "live" ? "live" : "muted";
}

function formatTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function parseEvidence(item: string) {
  const first = item.indexOf(":");
  if (first < 0) return { name: item, detail: "" };
  const name = item.slice(0, first).trim();
  const detail = item.slice(first + 1).trim();
  return { name, detail };
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      {sub && <small>{sub}</small>}
    </div>
  );
}

function SignalRow({ signal }: { signal: Signal }) {
  const tone = signalTone(signal.score);
  const width = Math.min(100, Math.max(4, Math.abs(signal.score) * 100));
  return (
    <div className="signal-row">
      <div className="signal-main">
        <div className="signal-name-line">
          <span className={`status-dot ${freshnessTone(signal.freshness)}`} />
          <strong>{signal.name}</strong>
          <span className={`signal-tag ${tone}`}>{tone.toUpperCase()}</span>
        </div>
        <small>{signal.detail}</small>
      </div>
      <div className="signal-weight">
        <span>W {Math.round(signal.weight * 100)}%</span>
      </div>
      <div className="signal-bar-wrap">
        <div className={`signal-bar ${tone}`} style={{ width: `${width}%` }} />
      </div>
      <b className={`signal-score ${tone}`}>{score(signal.score)}</b>
    </div>
  );
}

function EvidenceCard({ title, items, tone }: { title: string; items?: string[]; tone: "bull" | "bear" }) {
  return (
    <section className={`panel evidence-panel ${tone}`}>
      <div className="panel-head">
        <div>
          <span className="eyebrow">{tone === "bull" ? "UPWARD PRESSURE" : "DOWNWARD PRESSURE"}</span>
          <h3>{title}</h3>
        </div>
        <span className={`direction-chip ${tone}`}>{tone === "bull" ? "▲" : "▼"}</span>
      </div>
      <div className="evidence-list">
        {(items?.length ? items : ["No qualifying evidence detected"]).map((item, i) => {
          const parsed = parseEvidence(item);
          return (
            <div className="evidence-item" key={`${parsed.name}-${i}`}>
              <span className={`evidence-index ${tone}`}>{String(i + 1).padStart(2, "0")}</span>
              <div>
                <strong>{parsed.name}</strong>
                <small>{parsed.detail}</small>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LiquidityCard({ level, fallbackName }: { level?: LiquidityLevel; fallbackName: string }) {
  const isHigh = level?.side === "HIGH";
  const available = level?.price !== null && level?.price !== undefined;
  return (
    <div className={`liquidity-card ${isHigh ? "high" : "low"}`}>
      <div className="liq-top">
        <span>{level?.timeframe || fallbackName.replace(" ", " ").split(" ")[0]}</span>
        <span className="liq-side">{isHigh ? "HIGH" : "LOW"}</span>
      </div>
      <strong>{level?.price != null ? level.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</strong>
      <div className="liq-bottom">
        <span>{available ? (level?.status || "ACTIVE") : "AWAITING DATA"}</span>
        {level?.distance_pct != null && <span>{level.distance_pct.toFixed(2)}%</span>}
      </div>
    </div>
  );
}

type VisionLevel = {
  label: string;
  price: number | null;
  role: string;
  confidence: number;
};

type VisionAnalysis = {
  instrument: string;
  timeframe: string;
  current_price: number | null;
  direction: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNCLEAR";
  chart_confidence: number;
  confirmation_status: "PENDING" | "VISIBLE" | "UNCLEAR";
  structure: string;
  liquidity_read: string;
  long_scenario: string;
  short_scenario: string;
  levels: VisionLevel[];
  invalidation: string;
  rationale: string[];
  limitations: string[];
};

function ChartAnalysisLab({ forecast }: { forecast: Forecast | null }) {
  const [analysis, setAnalysis] = useState<UserAnalysis>({
    bias: "NEUTRAL",
    timeframe: "15M",
    notes: "",
    fileName: "",
    imageUrl: "",
  });
  const [vision, setVision] = useState<VisionAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const onFile = (file?: File) => {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const imageUrl = String(reader.result || "");
      setAnalysis((prev) => ({ ...prev, fileName: file.name, imageUrl }));
      setVision(null);
      setError("");
    };
    reader.readAsDataURL(file);
  };

  const submitForAnalysis = async () => {
    if (!analysis.imageUrl) {
      setError("پہلے chart upload کریں۔");
      return;
    }
    setBusy(true);
    setError("");
    setVision(null);
    try {
      const res = await fetch("/api/chart-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: analysis.imageUrl,
          context: {
            instrument: "NQ",
            timeframe: analysis.timeframe,
            fia_direction: forecast?.direction || "NEUTRAL",
            fia_bullish_probability: forecast?.bullish_probability ?? null,
            fia_bearish_probability: forecast?.bearish_probability ?? null,
            fia_confidence: forecast?.confidence ?? null,
            fia_data_coverage: forecast?.data_coverage ?? null,
          },
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.error || json?.detail || "Chart analysis failed");
      setVision(json.analysis);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chart analysis failed");
    } finally {
      setBusy(false);
    }
  };

  const fiaBias = forecast?.direction?.toUpperCase() || "NEUTRAL";
  const visionBias = vision?.direction || "UNCLEAR";
  const directionAligned = visionBias !== "UNCLEAR" && visionBias === fiaBias;
  const directionPartial = visionBias === "NEUTRAL" || fiaBias === "NEUTRAL";
  const verdict = !vision ? "AWAITING ANALYSIS" : directionAligned ? "ALIGNED" : directionPartial ? "PARTIAL" : "CONFLICT";
  const verdictClass = !vision ? "neutral" : directionAligned ? "bull" : directionPartial ? "neutral" : "bear";
  const fiaBull = forecast?.bullish_probability;
  const fiaBear = forecast?.bearish_probability;
  const visionBull = vision ? (vision.direction === "BULLISH" ? 100 : vision.direction === "BEARISH" ? 0 : 50) : null;
  const probabilityGap = vision && fiaBull != null && visionBull != null ? Math.abs(fiaBull - visionBull) : null;

  return (
    <section className="section-block chart-lab-block">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">MARKET ANALYSIS</span>
          <h2>Chart Review</h2>
        </div>
        <span className="coverage-chip">VISION AI</span>
      </div>

      <div className="chart-lab-grid">
        <div className="panel upload-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">01 · YOUR CHART</span>
              <h3>Upload Analysis Screenshot</h3>
            </div>
            <span className="upload-state">{analysis.imageUrl ? "ATTACHED" : "LOCAL"}</span>
          </div>

          <label className={`drop-zone ${analysis.imageUrl ? "has-image" : ""}`}>
            <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => onFile(e.target.files?.[0])} />
            {analysis.imageUrl ? (
              <img src={analysis.imageUrl} alt="Uploaded market analysis" />
            ) : (
              <>
                <strong>DROP CHART HERE</strong>
                <small>PNG · JPG · WEBP · Screenshot is sent only when you submit it for analysis.</small>
                <span className="upload-button">CHOOSE IMAGE</span>
              </>
            )}
          </label>
          {analysis.fileName && <div className="file-name">ATTACHED · {analysis.fileName}</div>}
        </div>

        <div className="panel analysis-input-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">02 · STRUCTURED VIEW</span>
              <h3>Tell FIA What You See</h3>
            </div>
            <span className="upload-state">{busy ? "ANALYZING" : "READY"}</span>
          </div>

          <div className="field-label">DIRECTIONAL BIAS</div>
          <div className="bias-selector">
            {(["BULLISH", "BEARISH", "NEUTRAL"] as const).map((bias) => (
              <button key={bias} className={analysis.bias === bias ? `active ${bias.toLowerCase()}` : ""} onClick={() => setAnalysis((p) => ({ ...p, bias }))}>
                {bias}
              </button>
            ))}
          </div>

          <label className="field-label" htmlFor="timeframe">TIMEFRAME</label>
          <select id="timeframe" value={analysis.timeframe} onChange={(e) => setAnalysis((p) => ({ ...p, timeframe: e.target.value }))}>
            {['1M','5M','15M','30M','1H','4H','1D'].map((tf) => <option key={tf}>{tf}</option>)}
          </select>

          <label className="field-label" htmlFor="notes">YOUR REASONING / LEVELS</label>
          <textarea id="notes" value={analysis.notes} onChange={(e) => setAnalysis((p) => ({ ...p, notes: e.target.value }))} placeholder="Support, resistance, liquidity, structure, entry idea, invalidation…" />

          <button className="analyze-chart-btn" onClick={submitForAnalysis} disabled={busy || !analysis.imageUrl}>
            {busy ? "ANALYZING CHART…" : "ANALYZE CHART WITH FIA AI"}
          </button>
          {error && <div className="vision-error">{error}</div>}
          <div className="vision-note">VISION = CHART INTERPRETATION ONLY · FIA MODEL REMAINS INDEPENDENT · NO CONFIRMATION IS IMPLIED BY PROBABILITY.</div>
        </div>

        <div className="panel comparison-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">03 · INDEPENDENT COMPARISON</span>
              <h3>FIA vs Chart Analysis</h3>
            </div>
            <span className={`verdict-chip ${verdictClass}`}>{verdict}</span>
          </div>

          {!vision ? (
            <div className="empty-analysis">Upload a chart and submit it. FIA will keep its model forecast separate from the visual reading.</div>
          ) : (
            <>
              <div className="compare-table">
                <div><span>Direction</span><b>{fiaBias}</b><b className={visionBias.toLowerCase()}>{visionBias}</b></div>
                <div><span>Timeframe</span><b>{forecast?.horizon_hours ? `${forecast.horizon_hours}H MODEL` : "—"}</b><b>{vision.timeframe}</b></div>
                <div><span>FIA Model Confidence</span><b>{forecast ? pct(forecast.confidence) : "—"}</b><b>—</b></div>
                <div><span>Chart Vision Confidence</span><b>—</b><b>{pct(vision.chart_confidence)}</b></div>
                <div><span>Confirmation</span><b>MODEL</b><b>{vision.confirmation_status}</b></div>
              </div>

              <div className="agreement-block">
                <div className="agreement-head"><span>DIRECTION ALIGNMENT</span><strong>{directionAligned ? "100%" : directionPartial ? "50%" : "0%"}</strong></div>
                <div className="agreement-track"><i style={{ width: `${directionAligned ? 100 : directionPartial ? 50 : 0}%` }} /></div>
                <small>{directionAligned ? "FIA model direction and chart vision agree." : directionPartial ? "One side is neutral; review the underlying evidence." : "Directional conflict detected. This is not a trade confirmation."}</small>
              </div>

              <div className="compare-metrics">
                <div><span>FIA BULLISH</span><b>{fiaBull != null ? pct(fiaBull) : "NOT AVAILABLE"}</b></div>
                <div><span>FIA BEARISH</span><b>{fiaBear != null ? pct(fiaBear) : "NOT AVAILABLE"}</b></div>
                <div><span>VISION BULLISH ESTIMATE</span><b>{visionBull != null ? pct(visionBull) : "NOT AVAILABLE"}</b></div>
                <div><span>PROBABILITY GAP</span><b>{probabilityGap != null ? `${probabilityGap.toFixed(1)} pts` : "NOT AVAILABLE"}</b></div>
              </div>

              <div className="scenario-box">
                <span className="eyebrow">SCENARIOS · NOT CONFIRMATIONS</span>
                <p><b>LONG:</b> {vision.long_scenario}</p>
                <p><b>SHORT:</b> {vision.short_scenario}</p>
                <p><b>INVALIDATION:</b> {vision.invalidation}</p>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

export default function Page() {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [liquidity, setLiquidity] = useState<LiquidityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      const [forecastRes, liquidityRes] = await Promise.all([
        fetch("/api/forecast", { cache: "no-store" }),
        fetch("/api/liquidity", { cache: "no-store" }),
      ]);

      if (!forecastRes.ok) throw new Error(`Forecast API returned ${forecastRes.status}`);
      const forecastJson = await forecastRes.json();
      const liquidityJson = liquidityRes.ok ? await liquidityRes.json() : null;

      setForecast(forecastJson);
      setLiquidity(liquidityJson);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load live intelligence");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(), 60000);
    return () => window.clearInterval(timer);
  }, [load]);

  const bullish = forecast?.bullish_probability ?? 50;
  const bearish = forecast?.bearish_probability ?? 50;
  const direction = forecast?.direction ?? "NEUTRAL";
  const directionClass = direction.toLowerCase();
  const coverage = (forecast?.data_coverage ?? 0) * 100;
  const intelligence = (forecast?.intelligence_coverage ?? 0) * 100;
  const signals = forecast?.signals ?? [];
  const bullSignals = useMemo(() => signals.filter(s => s.score > 0.08).length, [signals]);
  const bearSignals = useMemo(() => signals.filter(s => s.score < -0.08).length, [signals]);

  return (
    <main className="terminal-shell">
      <header className="topbar">
        <div className="brand">
          <div className="fia-mark">FIA</div>
          <div>
            <div className="brand-title">CLEAR NASDAQ</div>
            <div className="brand-sub">FORECAST INTELLIGENCE ENGINE</div>
          </div>
        </div>

        <div className="topbar-status">
          <span className="live-pill"><i /> LIVE DATA</span>
          <span className="api-pill">API ONLINE</span>
          <button className="refresh-btn" onClick={() => load(true)} disabled={refreshing}>
            <span className={refreshing ? "spin" : ""}>↻</span>
            {refreshing ? "SYNCING" : "REFRESH"}
          </button>
        </div>

        <div className="version">
          <span>CLEAR NASDAQ FIA</span>
          <b>v2.0.0</b>
        </div>
      </header>

      {error && <div className="error-banner">● {error}</div>}

      <section className="overview-grid">
        <aside className="panel system-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">SYSTEM STATUS</span>
              <h2>Market Intelligence</h2>
            </div>
            <span className="online-badge">ONLINE</span>
          </div>

          <div className="system-status">
            <div className="status-ring"><span>LIVE</span></div>
            <div>
              <strong>{forecast?.status || "CONNECTING"}</strong>
              <small>Forecast engine state</small>
            </div>
          </div>

          <div className="metric-stack">
            <Metric label="Confidence" value={pct(forecast?.confidence)} />
            <Metric label="Data Coverage" value={pct(coverage)} sub="Provider evidence" />
            <Metric label="Intelligence" value={pct(intelligence)} sub="Effective coverage" />
          </div>

          <div className="source-list">
            <div className="eyebrow">PROVIDER STATUS</div>
            {Object.entries(forecast?.source_status || {}).map(([key, value]) => (
              <div className="source-row" key={key}>
                <span>{key.replaceAll("_", " ")}</span>
                <b>{value}</b>
              </div>
            ))}
          </div>
        </aside>

        <section className={`panel hero-card ${directionClass}`}>
          <div className="hero-glow" />
          <div className="hero-top">
            <div>
              <span className="eyebrow">NASDAQ FORECAST · {forecast?.symbol || "NQ"}</span>
              <div className="hero-meta">
                <span>{forecast?.horizon_hours ?? 8}H HORIZON</span>
                <span>•</span>
                <span>{forecast?.regime || "BALANCED"} REGIME</span>
              </div>
            </div>
            <div className={`direction-badge ${directionClass}`}>
              <span className="direction-icon">{direction === "BULLISH" ? "▲" : direction === "BEARISH" ? "▼" : "●"}</span>
              <div>
                <strong>{direction}</strong>
                <small>MODEL DIRECTION</small>
              </div>
            </div>
          </div>

          <div className="hero-center">
            <div className="score-block">
              <span className="eyebrow">MODEL SCORE</span>
              <strong>{score(forecast?.score)}</strong>
              <small>{forecast?.regime || "BALANCED"} intelligence regime</small>
            </div>

            <div className="probability">
              <div className="prob-row">
                <span>BULLISH</span><b>{pct(bullish)}</b>
              </div>
              <div className="prob-track">
                <div className="bull-fill" style={{ width: `${bullish}%` }} />
              </div>
              <div className="prob-row bearish-label">
                <span>BEARISH</span><b>{pct(bearish)}</b>
              </div>
              <div className="prob-track">
                <div className="bear-fill" style={{ width: `${bearish}%` }} />
              </div>
            </div>
          </div>

          <div className="hero-foot">
            <div><span>GENERATED</span><b>{formatTime(forecast?.generated_at)}</b></div>
            <div><span>LIVE SIGNALS</span><b>{signals.length}</b></div>
            <div><span>BIAS SPLIT</span><b>{bullSignals} / {bearSignals}</b></div>
          </div>
        </section>
      </section>

      <section className="panel thesis-panel">
        <div className="section-kicker"><span className="kicker-line" /> FIA MARKET THESIS</div>
        <h2>{forecast?.thesis || "Awaiting live market intelligence..."}</h2>
        <div className="thesis-stats">
          <span><i className="dot bull" /> Bullish evidence <b>{bullSignals}</b></span>
          <span><i className="dot bear" /> Bearish evidence <b>{bearSignals}</b></span>
          <span><i className="dot neutral" /> Total signals <b>{signals.length}</b></span>
        </div>
      </section>

      <section className="section-block">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">MARKET COMPONENTS</span>
            <h2>Signal Matrix</h2>
          </div>
          <div className="matrix-legend">
            <span><i className="dot bull" /> Bullish</span>
            <span><i className="dot bear" /> Bearish</span>
            <span><i className="dot neutral" /> Neutral</span>
          </div>
        </div>

        <div className="panel signal-panel">
          <div className="signal-header">
            <span>SIGNAL</span><span>WEIGHT</span><span>IMPACT</span><span>SCORE</span>
          </div>
          {loading && !signals.length ? (
            <div className="loading-state">Loading live signal intelligence…</div>
          ) : signals.length ? (
            signals.map((signal) => <SignalRow signal={signal} key={signal.name} />)
          ) : (
            <div className="loading-state">No signals available.</div>
          )}
        </div>
      </section>

      <section className="section-block">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">EVIDENCE INTELLIGENCE</span>
            <h2>Why FIA Has This Bias</h2>
          </div>
          <span className="coverage-chip">{pct(intelligence)} COVERAGE</span>
        </div>
        <div className="evidence-grid">
          <EvidenceCard title="Bullish Evidence" items={forecast?.bullish_evidence} tone="bull" />
          <EvidenceCard title="Bearish Evidence" items={forecast?.bearish_evidence} tone="bear" />
        </div>
      </section>

      <section className="section-block">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">LIQUIDITY INTELLIGENCE</span>
            <h2>Liquidity Map</h2>
          </div>
          <span className="coverage-chip">{liquidity?.status || "LIVE"}</span>
        </div>
        <div className="liquidity-grid">
          {liquidityKeys.map((key) => (
            <LiquidityCard
              key={key}
              level={liquidity?.levels?.[key]}
              fallbackName={labelMap[key]}
            />
          ))}
        </div>
        <div className="liquidity-note">
          <span>Liquidity provider</span>
          <b>{liquidity?.provider || "Finnhub"}</b>
          <span>•</span>
          <span>Levels shown when provider data is available.</span>
        </div>
      </section>

      <ChartAnalysisLab forecast={forecast} />

      <section className="section-block invalidation-block">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">RISK CONTROL</span>
            <h2>Forecast Invalidation</h2>
          </div>
          <span className="risk-chip">MONITOR</span>
        </div>
        <div className="invalidation-grid">
          {(forecast?.invalidation || []).map((item, i) => (
            <div className="invalidation-item" key={item}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              <p>{item}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="footer">
        <span>CLEAR NASDAQ FIA · FORECAST ENGINE · EVIDENCE INTELLIGENCE</span>
        <span>LIVE MARKET DATA · {forecast?.source_status?.market || "CONNECTING"}</span>
      </footer>
    </main>
  );
}
