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

type PerformanceCell = {
  resolved?: number;
  correct?: number;
  accuracy_pct?: number;
};

type BackendMeta = {
  ok: boolean;
  service: string;
  version: string;
  prediction_ledger?: {
    total: number;
    resolved: number;
    unresolved: number;
    correct: number;
    accuracy_pct: number | null;
    latest_timestamp?: string;
  };
  phase_statuses?: Array<{
    phase: string;
    status: string;
    detail?: Record<string, unknown>;
  }>;
  phase21?: {
    forecasts_created?: number;
    errors_count?: number;
    resolved_4h?: number;
    accuracy_4h_pct?: number;
    resolved_8h?: number;
    accuracy_8h_pct?: number;
    brier_4h?: number;
    brier_8h?: number;
    predictions?: Record<string, number>;
    regimes?: Record<string, number>;
    monthly_performance?: Record<string, {
      forecasts?: number;
      "4h"?: PerformanceCell;
      "8h"?: PerformanceCell;
    }>;
    earnings_event_day_performance?: Record<string, {
      count?: number;
      "4h"?: PerformanceCell;
      "8h"?: PerformanceCell;
    }>;
  };
};

const configuredApi = process.env.NEXT_PUBLIC_FIA_API_URL?.replace(/\/$/, "");
const apiCandidates = [
  configuredApi,
  "http://127.0.0.1:8001",
  "http://127.0.0.1:8000",
].filter((value, index, all): value is string => Boolean(value) && all.indexOf(value) === index);

async function resolveApiBase() {
  for (const base of apiCandidates) {
    try {
      const response = await fetch(`${base}/api/health`, { cache: "no-store" });
      if (response.ok) return base;
    } catch {
      // Try the next local backend port.
    }
  }
  throw new Error("FIA backend is offline on ports 8001 and 8000");
}

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

function ChartAnalysisLab({ forecast, apiBase }: { forecast: Forecast | null; apiBase: string }) {
  const [analysis, setAnalysis] = useState<UserAnalysis>({
    bias: "NEUTRAL",
    timeframe: "15M",
    notes: "",
    fileName: "",
    imageUrl: "",
  });

  const [analyzing, setAnalyzing] = useState(false);
  const [visionResult, setVisionResult] = useState<any>(null);
  const [visionError, setVisionError] = useState("");

  const onFile = (file?: File) => {
    if (!file || !file.type.startsWith("image/")) return;

    if (analysis.imageUrl) {
      URL.revokeObjectURL(analysis.imageUrl);
    }

    const imageUrl = URL.createObjectURL(file);

    setAnalysis((prev) => ({
      ...prev,
      fileName: file.name,
      imageUrl,
    }));

    setVisionResult(null);
    setVisionError("");
  };

  const analyzeChart = async () => {
    if (!analysis.fileName) {
      setVisionError("Please upload a chart screenshot first.");
      return;
    }

    setAnalyzing(true);
    setVisionError("");
    setVisionResult(null);

    try {
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement | null;

      const file = input?.files?.[0];

      if (!file) {
        throw new Error("Chart file is no longer available. Please select it again.");
      }

      const formData = new FormData();
      formData.append("file", file);

      formData.append(
        "bias",
        analysis.bias
      );

      formData.append(
        "timeframe",
        analysis.timeframe
      );

      formData.append(
        "notes",
        analysis.notes
      );

      const response = await fetch(
        `${apiBase}/api/chart/analyze`,
        {
          method: "POST",
          body: formData,
        }
      );

      const text = await response.text();

      let data: any;

      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(
          `Backend returned an invalid response (${response.status}).`
        );
      }

      if (!response.ok) {
        throw new Error(
          data?.detail ||
          data?.error ||
          `Chart analysis failed (${response.status}).`
        );
      }

      setVisionResult(data);
    } catch (error: any) {
      setVisionError(
        error?.message ||
        "Unable to connect to the Vision Engine."
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const fiaBias =
    String(
      forecast?.direction ||
      forecast?.direction ||
      "NEUTRAL"
    ).toUpperCase();

  const userBias = analysis.bias;

  const agreement =
    userBias === fiaBias
      ? 100
      : userBias === "NEUTRAL" || fiaBias === "NEUTRAL"
        ? 50
        : 0;

  const verdict =
    userBias === fiaBias
      ? "ALIGNED"
      : userBias === "NEUTRAL" || fiaBias === "NEUTRAL"
        ? "PARTIAL / NEUTRAL"
        : "CONFLICT";

  const verdictClass =
    agreement === 100
      ? "aligned"
      : agreement === 50
        ? "partial"
        : "conflict";

  const visionDirection =
    String(
      visionResult?.direction ||
      visionResult?.analysis?.direction ||
      "—"
    ).toUpperCase();

  const visionConfidence =
    visionResult?.confidence ??
    visionResult?.analysis?.confidence ??
    null;

  return (
    <section className="section-block chart-lab-section">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">MARKET ANALYSIS</span>
          <h2>CHART REVIEW</h2>
        </div>
        <span className="risk-chip">VISION AI</span>
      </div>

      <div className="chart-lab-grid">

        <div className="panel upload-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">01 · YOUR CHART</span>
              <h3>Upload Analysis Screenshot</h3>
            </div>
            <span className="upload-state">
              {analysis.imageUrl ? "ATTACHED" : "LOCAL"}
            </span>
          </div>

          <label className={`drop-zone ${analysis.imageUrl ? "has-image" : ""}`}>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => onFile(e.target.files?.[0])}
            />

            {analysis.imageUrl ? (
              <img
                src={analysis.imageUrl}
                alt="Uploaded market analysis"
              />
            ) : (
              <>
                <strong>DROP CHART HERE</strong>
                <small>
                  PNG · JPG · WEBP · Select your trading chart screenshot.
                </small>
                <span className="upload-button">
                  CHOOSE IMAGE
                </span>
              </>
            )}
          </label>

          {analysis.fileName && (
            <div className="file-name">
              ATTACHED · {analysis.fileName}
            </div>
          )}

          <button
            type="button"
            className="chart-analyze-button"
            onClick={analyzeChart}
            disabled={!analysis.imageUrl || analyzing}
          >
            {analyzing ? "ANALYZING CHART…" : "ANALYZE CHART WITH FIA AI"}
          </button>

          {visionError && (
            <div className="chart-error">
              ● {visionError}
            </div>
          )}
        </div>

        <div className="panel analysis-input-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">02 · STRUCTURED VIEW</span>
              <h3>Tell FIA What You See</h3>
            </div>
            <span className="upload-state">
              {visionResult ? "ANALYZED" : "READY"}
            </span>
          </div>

          <div className="field-label">
            DIRECTIONAL BIAS
          </div>

          <div className="bias-selector">
            {(["BULLISH", "BEARISH", "NEUTRAL"] as const).map((bias) => (
              <button
                type="button"
                key={bias}
                className={
                  analysis.bias === bias
                    ? `active ${bias.toLowerCase()}`
                    : ""
                }
                onClick={() =>
                  setAnalysis((p) => ({
                    ...p,
                    bias,
                  }))
                }
              >
                {bias}
              </button>
            ))}
          </div>

          <label
            className="field-label"
            htmlFor="timeframe"
          >
            TIMEFRAME
          </label>

          <select
            id="timeframe"
            value={analysis.timeframe}
            onChange={(e) =>
              setAnalysis((p) => ({
                ...p,
                timeframe: e.target.value,
              }))
            }
          >
            {["1M", "5M", "15M", "30M", "1H", "4H", "1D"].map((tf) => (
              <option key={tf}>{tf}</option>
            ))}
          </select>

          <label
            className="field-label"
            htmlFor="notes"
          >
            YOUR REASONING / LEVELS
          </label>

          <textarea
            id="notes"
            value={analysis.notes}
            onChange={(e) =>
              setAnalysis((p) => ({
                ...p,
                notes: e.target.value,
              }))
            }
            placeholder="Support, resistance, liquidity, structure, entry idea, invalidation…"
          />

          <div className="vision-note">
            {visionResult
              ? "VISION ENGINE · IMAGE INTERPRETED · OPENAI VISION"
              : "VISION ENGINE · SELECT A CHART AND RUN ANALYSIS"}
          </div>
        </div>

        <div className="panel comparison-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">
                03 · INDEPENDENT COMPARISON
              </span>
              <h3>FIA vs Your Analysis</h3>
            </div>

            <span className={`verdict-chip ${verdictClass}`}>
              {verdict}
            </span>
          </div>

          <div className="compare-table">
            <div>
              <span>Direction</span>
              <b>{fiaBias}</b>
              <b className={analysis.bias.toLowerCase()}>
                {analysis.bias}
              </b>
            </div>

            <div>
              <span>Timeframe</span>
              <b>
                {forecast?.horizon_hours
                  ? `${forecast.horizon_hours}H`
                  : "—"}
              </b>
              <b>{analysis.timeframe}</b>
            </div>

            <div>
              <span>Confidence</span>
              <b>
                {forecast
                  ? pct(forecast.confidence)
                  : "—"}
              </b>
              <b>USER INPUT</b>
            </div>
          </div>

          <div className="agreement-block">
            <div className="agreement-head">
              <span>BIAS AGREEMENT</span>
              <strong>{agreement}%</strong>
            </div>

            <div className="agreement-track">
              <i style={{ width: `${agreement}%` }} />
            </div>

            <small>
              {agreement === 100
                ? "Your directional view matches FIA."
                : agreement === 50
                  ? "One side is neutral; review the underlying evidence."
                  : "Directional conflict detected. Compare structure, news and macro evidence before acting."}
            </small>
          </div>

          {visionResult && (
            <div className="vision-result">
              <div className="eyebrow">
                FIA VISION RESULT
              </div>

              <div className="vision-result-grid">
                <div>
                  <span>DIRECTION</span>
                  <strong>{visionDirection}</strong>
                </div>

                <div>
                  <span>CONFIDENCE</span>
                  <strong>
                    {visionConfidence !== null
                      ? `${Number(visionConfidence).toFixed(1)}%`
                      : "—"}
                  </strong>
                </div>
              </div>

              {(visionResult?.summary ||
                visionResult?.analysis?.summary) && (
                <p>
                  {visionResult.summary ||
                    visionResult.analysis.summary}
                </p>
              )}

              <div className="full-comparison">
                <div className="eyebrow">FULL FIA VS GEMINI COMPARISON</div>

                <div className="vision-result-grid">
                  <div>
                    <span>FIA DIRECTION</span>
                    <strong>{String(
                      visionResult?.comparison?.fia_direction ||
                      forecast?.direction ||
                      "NEUTRAL"
                    ).toUpperCase()}</strong>
                  </div>

                  <div>
                    <span>GEMINI DIRECTION</span>
                    <strong>
                      {String(
                        visionResult?.comparison?.user_direction ||
                        visionResult?.direction ||
                        visionResult?.analysis?.direction ||
                        "NEUTRAL"
                      ).toUpperCase()}
                    </strong>
                  </div>

                  <div>
                    <span>FIA CONFIDENCE</span>
                    <strong>
                      {forecast?.confidence != null
                        ? `${Number(forecast.confidence).toFixed(1)}%`
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <span>GEMINI CONFIDENCE</span>
                    <strong>
                      {(
                        visionResult?.confidence ??
                        visionResult?.analysis?.confidence
                      ) != null
                        ? `${Number(
                            visionResult.confidence ??
                            visionResult.analysis.confidence
                          )}%`
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <span>PROBABILITY GAP</span>
                    <strong>
                      {visionResult?.comparison?.probability_gap ?? "—"}
                    </strong>
                  </div>

                  <div>
                    <span>COMPARISON SCORE</span>
                    <strong>
                      {visionResult?.comparison?.comparison_score ?? "—"}
                    </strong>
                  </div>

                  <div>
                    <span>DIRECTION ALIGNMENT</span>
                    <strong>
                      {visionResult?.comparison?.direction_alignment ?? "—"}
                    </strong>
                  </div>

                  <div>
                    <span>FIA BULLISH PROBABILITY</span>
                    <strong>
                      {visionResult?.comparison?.fia_bullish_probability ?? "—"}
                    </strong>
                  </div>

                  <div>
                    <span>GEMINI BULLISH ESTIMATE</span>
                    <strong>
                      {visionResult?.comparison?.user_bullish_probability_estimate ?? "—"}
                    </strong>
                  </div>
                </div>

                {(visionResult?.note ||
                  visionResult?.comparison?.note) && (
                  <div className="vision-note">
                    {visionResult.note ||
                      visionResult.comparison.note}
                  </div>
                )}
              </div>

              {(visionResult?.key_levels ||
                visionResult?.analysis?.key_levels) && (
                <div className="vision-levels">
                  <span className="eyebrow">
                    KEY LEVELS
                  </span>

                  <pre>
                    {JSON.stringify(
                      visionResult.key_levels ||
                        visionResult.analysis.key_levels,
                      null,
                      2
                    )}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
export default function Page() {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [liquidity, setLiquidity] = useState<LiquidityResponse | null>(null);
  const [backendMeta, setBackendMeta] = useState<BackendMeta | null>(null);
  const [apiBase, setApiBase] = useState(configuredApi || "http://127.0.0.1:8001");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      const activeBase = await resolveApiBase();
      setApiBase(activeBase);
      const [forecastRes, liquidityRes, metaRes] = await Promise.all([
        fetch(`${activeBase}/api/forecast`, { cache: "no-store" }),
        fetch(`${activeBase}/api/liquidity`, { cache: "no-store" }),
        fetch(`${activeBase}/api/dashboard/meta`, { cache: "no-store" }),
      ]);

      if (!forecastRes.ok) throw new Error(`Forecast API returned ${forecastRes.status}`);
      const forecastJson = await forecastRes.json();
      const liquidityJson = liquidityRes.ok ? await liquidityRes.json() : null;
      const metaJson = metaRes.ok ? await metaRes.json() : null;

      setForecast(forecastJson);
      setLiquidity(liquidityJson);
      setBackendMeta(metaJson);
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
  const phase21 = backendMeta?.phase21;
  const monthlyRows = Object.entries(phase21?.monthly_performance || {}).sort(([a], [b]) => a.localeCompare(b));
  const earningsRows = Object.entries(phase21?.earnings_event_day_performance || {});

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
          <span className={`api-pill ${error ? "offline" : ""}`}>{error ? "API OFFLINE" : "API ONLINE"}</span>
          <button className="refresh-btn" onClick={() => load(true)} disabled={refreshing}>
            <span className={refreshing ? "spin" : ""}>↻</span>
            {refreshing ? "SYNCING" : "REFRESH"}
          </button>
        </div>

        <div className="version">
          <span>CLEAR NASDAQ FIA</span>
          <b>v{backendMeta?.version || "2.1.0"}</b>
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

      <section className="section-block">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">BACKEND OPERATIONS</span>
            <h2>Phase 21 Backtest Scorecard</h2>
          </div>
          <span className="coverage-chip">{phase21?.errors_count ?? 0} ERRORS</span>
        </div>

        <div className="scorecard-grid">
          <Metric label="Forecasts" value={String(phase21?.forecasts_created ?? "—")} sub="1-year replay" />
          <Metric label="4H Accuracy" value={phase21?.accuracy_4h_pct != null ? pct(phase21.accuracy_4h_pct) : "—"} sub={`${phase21?.resolved_4h ?? 0} resolved`} />
          <Metric label="8H Accuracy" value={phase21?.accuracy_8h_pct != null ? pct(phase21.accuracy_8h_pct) : "—"} sub={`${phase21?.resolved_8h ?? 0} resolved`} />
          <Metric label="4H Brier" value={phase21?.brier_4h != null ? phase21.brier_4h.toFixed(3) : "—"} sub="probability error" />
          <Metric label="8H Brier" value={phase21?.brier_8h != null ? phase21.brier_8h.toFixed(3) : "—"} sub="probability error" />
          <Metric label="Live Ledger" value={String(backendMeta?.prediction_ledger?.total ?? "—")} sub={`${backendMeta?.prediction_ledger?.unresolved ?? 0} awaiting resolution`} />
        </div>

        <div className="backend-grid">
          <section className="panel backend-panel">
            <div className="panel-head">
              <div><span className="eyebrow">MONTHLY PERFORMANCE</span><h3>Accuracy History</h3></div>
              <span className="upload-state">{monthlyRows.length} MONTHS</span>
            </div>
            <div className="performance-table">
              <div className="performance-head"><span>MONTH</span><span>FORECASTS</span><span>4H</span><span>8H</span></div>
              {monthlyRows.map(([month, row]) => (
                <div className="performance-row" key={month}>
                  <b>{month}</b>
                  <span>{row.forecasts ?? "—"}</span>
                  <span>{row["4h"]?.accuracy_pct != null ? pct(row["4h"]?.accuracy_pct) : "—"}</span>
                  <span>{row["8h"]?.accuracy_pct != null ? pct(row["8h"]?.accuracy_pct) : "—"}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel backend-panel">
            <div className="panel-head">
              <div><span className="eyebrow">CONTEXT ACCURACY</span><h3>Earnings vs Other Days</h3></div>
              <span className="upload-state">VERIFIED</span>
            </div>
            <div className="event-performance">
              {earningsRows.map(([name, row]) => (
                <div className="event-card" key={name}>
                  <span>{name.replaceAll("_", " ")}</span>
                  <strong>{row["4h"]?.accuracy_pct != null ? pct(row["4h"]?.accuracy_pct) : "—"}</strong>
                  <small>4H · {row.count ?? 0} DAYS</small>
                  <b>{row["8h"]?.accuracy_pct != null ? pct(row["8h"]?.accuracy_pct) : "—"} 8H</b>
                </div>
              ))}
            </div>
            <div className="phase-list">
              <div className="eyebrow">BACKTEST MODULE HEALTH</div>
              {(backendMeta?.phase_statuses || []).map((phase) => (
                <div className="phase-row" key={phase.phase}>
                  <span>{phase.phase}</span><b>{String(phase.status).toUpperCase()}</b>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>

      <ChartAnalysisLab forecast={forecast} apiBase={apiBase} />

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
