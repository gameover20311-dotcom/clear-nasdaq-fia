"use client";

/* CLEAR NASDAQ — CHART LAB
 *
 * Upload a chart -> INDEPENDENT vision read -> comparison against verified FIA
 * evidence. The vision model never sees FIA's direction or the user's opinion.
 *
 * Product UI text is English only.
 *
 * The two evidence worlds are kept visually and structurally apart:
 *   CHART   = read from the uploaded image. An opinion about pixels.
 *   BACKEND = verified live FIA evidence.
 * Every claim carries its origin, and nothing chart-derived is presented as
 * market truth.
 */

import Link from "next/link";
import { useMemo, useRef, useState } from "react";

type Obj = Record<string, any>;

const asObj = (v: any): Obj => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const asList = (v: any): any[] => (Array.isArray(v) ? v : []);
const finite = (v: any): number | null => {
  if (v === null || v === undefined || typeof v === "boolean") return null;
  if (typeof v === "string" && v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const pct = (v: any, d = 2) => {
  const n = finite(v);
  return n === null ? "—" : `${n.toFixed(d)}%`;
};
const num = (v: any, d = 2) => {
  const n = finite(v);
  return n === null ? "—" : n.toFixed(d);
};
const words = (v: any) => String(v ?? "—").replace(/_/g, " ");
const upper = (v: any) => String(v ?? "").toUpperCase();
const dirColor = (d: any) =>
  upper(d) === "BULLISH" ? "var(--bull)" : upper(d) === "BEARISH" ? "var(--bear)" : "var(--t-mid)";

const AGREEMENT_TONE: Record<string, string> = {
  CONFIRMS: "good",
  PARTIAL: "mid",
  CONFLICTS: "bad",
  INSUFFICIENT_DATA: "neutral",
};
const USER_TONE: Record<string, string> = {
  AGREES: "good",
  PARTIALLY_AGREES: "mid",
  DISAGREES: "bad",
  INSUFFICIENT_EVIDENCE: "neutral",
};

const TIMEFRAMES = ["1M", "5M", "15M", "30M", "1H", "4H", "1D"];

export default function ChartLab() {
  const [file, setFile] = useState<File | null>(null);
  const [direction, setDirection] = useState("BULLISH");
  const [timeframe, setTimeframe] = useState("15M");
  const [reasoning, setReasoning] = useState("");
  const [report, setReport] = useState<Obj | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);

  const headline = asObj(report?.headline);
  const chartRead = asObj(headline.chart_read);
  const fiaRead = asObj(headline.fia_read);
  const agreement = asObj(headline.agreement);
  const setup = asObj(headline.setup_quality);
  const invalidation = asObj(headline.invalidation);
  const chartOnly = asObj(report?.chart_only);
  const backend = asObj(report?.verified_backend);
  const userCmp = asObj(report?.user_comparison);
  const backendErrors = asList(report?.backend_evidence_errors);

  const features = useMemo(() => asList(chartOnly.features), [chartOnly]);

  async function analyze() {
    if (!file) {
      setError("Select a chart image to begin.");
      return;
    }
    setBusy(true);
    setError("");
    setReport(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("user_direction", direction);
      form.append("user_timeframe", timeframe);
      form.append("user_reasoning", reasoning);

      const response = await fetch("/api/fia/chart-analyst", { method: "POST", body: form });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.ok !== true) {
        throw new Error(payload?.detail || payload?.error || `Chart analyst failed (HTTP ${response.status})`);
      }
      setReport(payload);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <div className="brand-mark"><span className="brand-dot" /><span className="brand-name">CLEAR NASDAQ</span></div>
          <div className="brand-sub">CHART LAB · INDEPENDENT VISION</div>
        </div>
        <nav className="nav" aria-label="Primary">
          <Link href="/" className="nav-item" style={{ textDecoration: "none" }}>
            <span className="idx">←</span><span className="lbl">Cockpit</span><span className="sub">Back to the dashboard</span>
          </Link>
          <div className="nav-div">Tools</div>
          <span className="nav-item" aria-current="page">
            <span className="idx">↗</span><span className="lbl">Chart Lab</span><span className="sub">Upload · vision · confluence</span>
          </span>
        </nav>
        <div className="rail-foot"><p className="hint">Research analysis only. Never an order instruction.</p></div>
      </aside>

      <div className="main">
        <div className="topbar">
          <span className="tb"><span className="tb-k">Module</span><span className="tb-v">Chart Analyst</span></span>
          <span className="tb-sep" />
          <span className="tb"><span className="dot warn" /><span className="tb-k">Vision</span><span className="tb-v">External paid API</span></span>
          <span className="tb-sp" />
          <span className="tb"><span className="tb-k">Forecast path</span><span className="tb-v">Local model only</span></span>
        </div>

        <section className="page active">
          <div className="page-head">
            <div>
              <h1 className="page-title">Chart Lab</h1>
              <p className="page-desc">
                The vision model reads your chart before it is shown FIA&rsquo;s direction or yours. Only afterwards is the
                reading compared with verified backend evidence.
              </p>
            </div>
          </div>

          <div className="degraded" style={{ marginBottom: 12 }}>
            <span className="k">DISCLOSURE</span>
            <span className="v">
              This workflow calls an <b>external paid vision API</b>, unlike the forecast path which runs on the local model
              only. Chart-derived observations are labelled <b>CHART</b> and are never presented as verified market data.
              Verified backend evidence is labelled <b>BACKEND</b>.
            </span>
          </div>

          {/* ---------------------------------------------------- INPUT */}
          <div className="cl-grid">
            <div className="cl-card">
              <div className="cl-step">01 · Your chart</div>
              <h4>Upload analysis screenshot</h4>
              <label className="cl-drop">
                <input
                  ref={fileInput}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  style={{ display: "none" }}
                  onChange={(e) => { setFile(e.target.files?.[0] || null); setError(""); }}
                />
                <strong>{file ? file.name : "CHOOSE PNG / JPG / WEBP"}</strong>
                <span>Vision will not see FIA&rsquo;s direction.</span>
              </label>
              <p className="hint">Select a chart image to begin.</p>
            </div>

            <div className="cl-card">
              <div className="cl-step">02 · Your independent plan</div>
              <h4>Tell FIA what you see</h4>
              <div className="cl-row">
                {["BULLISH", "BEARISH", "NEUTRAL"].map((d) => (
                  <button key={d} aria-pressed={direction === d} onClick={() => setDirection(d)}>{d}</button>
                ))}
              </div>
              <select className="cl-sel" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} aria-label="Timeframe">
                {TIMEFRAMES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <textarea
                className="cl-ta"
                value={reasoning}
                onChange={(e) => setReasoning(e.target.value)}
                placeholder="Example: HTF demand POI, Asia liquidity swept, 1m CHoCH + displacement..."
              />
            </div>

            <div className="cl-card">
              <div className="cl-step">03 · Run independent check</div>
              <h4>Vision, then FIA comparison</h4>
              <button className="cl-run" onClick={analyze} disabled={busy}>
                {busy ? "ANALYSING…" : "ANALYSE WITH FIA"}
              </button>
              {error && (
                <div style={{ padding: "9px 11px", border: "1px solid var(--bear-br)", background: "var(--bear-bg)", borderRadius: "var(--r)", color: "var(--bear)", fontSize: 11 }}>
                  {error}
                </div>
              )}
              <p className="hint">Research only · Broker execution OFF · Setup grades remain OOS-validation gated.</p>
            </div>
          </div>

          {/* ------------------------------------------------- HEADLINE */}
          {report && (
            <>
              <div className="state-row four" style={{ marginTop: 14 }}>
                <div className="state-cell">
                  <div className="sc-b">
                    <div className="sc-k">1 · Chart read <span className="badge neutral" style={{ marginLeft: 6 }}>CHART</span></div>
                    <div className="sc-v"><span className="sc-n" style={{ color: dirColor(chartRead.direction) }}>{upper(words(chartRead.direction))}</span></div>
                    <div className="sc-note">Readability {words(chartRead.readability)} · clarity {pct(chartRead.clarity_confidence, 1)}</div>
                  </div>
                </div>
                <div className="state-cell">
                  <div className="sc-b">
                    <div className="sc-k">2 · FIA read <span className="badge info" style={{ marginLeft: 6 }}>BACKEND</span></div>
                    <div className="sc-v">
                      <span className="sc-n" style={{ color: dirColor(fiaRead.direction_8h) }}>{upper(words(fiaRead.direction_8h))}</span>
                      <span className="badge mid">{upper(words(fiaRead.state))}</span>
                    </div>
                    <div className="sc-note">
                      8H {pct(fiaRead.bullish_probability_8h, 2)} · conf {pct(fiaRead.confidence_8h, 2)} — 4H {pct(fiaRead.bullish_probability_4h, 2)} · conf {pct(fiaRead.confidence_4h, 2)}
                    </div>
                  </div>
                </div>
                <div className="state-cell">
                  <div className="sc-b">
                    <div className="sc-k">3 · Agreement</div>
                    <div className="sc-v">
                      <span className={`badge ${AGREEMENT_TONE[upper(agreement.verdict)] || "neutral"}`}>{upper(words(agreement.verdict))}</span>
                    </div>
                    <div className="sc-note">{asList(agreement.reasons)[0] || "—"}</div>
                  </div>
                </div>
                <div className="state-cell">
                  <div className="sc-b">
                    <div className="sc-k">4 · Setup quality</div>
                    <div className="sc-v"><span className="sc-n">{upper(words(setup.grade))}</span></div>
                    <div className="sc-note">Descriptive research label — not a probability or win rate.</div>
                  </div>
                </div>
              </div>

              <div className="cockpit">
                <div className="stack">
                  {/* 5 · KEY REASONS */}
                  <div className="panel">
                    <div className="panel-h"><div><h3>5 · Key reasons</h3><p className="hint" style={{ marginTop: 1 }}>Strongest points only. Each tagged with its origin.</p></div></div>
                    <div className="panel-b">
                      {asList(headline.key_reasons).map((raw: any, i: number) => {
                        const r = asObj(raw);
                        const isChart = upper(r.origin) === "CHART";
                        return (
                          <div className="ev" key={i} style={{ gridTemplateColumns: "2px 1fr" }}>
                            <span className="ev-w" style={{ background: isChart ? "var(--warn)" : "var(--cyan)" }} />
                            <div>
                              <p className="ev-t">{String(r.text)}</p>
                              <div className="ev-m"><span className={`badge ${isChart ? "mid" : "info"}`}>{upper(r.origin)}</span></div>
                            </div>
                          </div>
                        );
                      })}
                      {asList(setup.blockers).length > 0 && (
                        <div className="degraded" style={{ marginTop: 10 }}>
                          <span className="k">BLOCKERS</span>
                          <span className="v">{asList(setup.blockers).join(" ")}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 6 · INVALIDATION */}
                  <div className="panel inv">
                    <div className="panel-h"><span className="inv-q">6 · WHAT WOULD INVALIDATE THIS?</span></div>
                    <div className="panel-b">
                      <div className="eyebrow" style={{ marginBottom: 6 }}>Visible in the chart <span className="badge mid" style={{ marginLeft: 6 }}>CHART</span></div>
                      <p className="inv-b" style={{ fontSize: 11.5 }}>{words(asObj(invalidation.visible_in_chart).condition)}</p>
                      <div className="eyebrow" style={{ margin: "14px 0 6px" }}>Verified from backend <span className="badge info" style={{ marginLeft: 6 }}>BACKEND</span></div>
                      <div className="inv-l">
                        {asList(asObj(invalidation.verified_from_backend).conditions).map((c: any, i: number) => (
                          <div className="inv-i" key={i}><span className="inv-x num">{String(i + 1).padStart(2, "0")}</span><p className="inv-t">{String(c)}</p></div>
                        ))}
                      </div>
                      {asList(asObj(invalidation.verified_from_backend).conditions).length === 0 && (
                        <p className="hint">No backend invalidation conditions were returned.</p>
                      )}
                    </div>
                  </div>

                  {/* CHART STRUCTURE */}
                  <div className="panel">
                    <div className="panel-h">
                      <div><h3>Chart structure <span className="badge mid">CHART ONLY</span></h3><p className="hint" style={{ marginTop: 1 }}>Read from pixels. Anything unsupported is NOT_CONFIRMED, not assumed absent.</p></div>
                    </div>
                    <div className="panel-b">
                      <div className="cl-feat">
                        {features.map((raw: any, i: number) => {
                          const f = asObj(raw);
                          const on = upper(f.state) === "DETECTED";
                          return (
                            <div className={`cl-f ${on ? "on" : ""}`} key={i} title={String(f.note || "")}>
                              <span>{String(f.label ?? f.key)}</span>
                              <b>{on ? "DETECTED" : "NOT CONFIRMED"}</b>
                            </div>
                          );
                        })}
                      </div>
                      <div className="kv" style={{ marginTop: 12 }}><span className="k">Instrument visible</span><span className="v">{words(chartOnly.instrument_visible)}</span></div>
                      <div className="kv"><span className="k">Timeframes visible</span><span className="v">{asList(chartOnly.timeframes_visible).join(" · ") || "—"}</span></div>
                      <div className="kv"><span className="k">Chart direction</span><span className="v" style={{ color: dirColor(chartOnly.direction) }}>{upper(words(chartOnly.direction))}</span></div>
                      <div className="kv"><span className="k">Chart clarity</span><span className="v num">{pct(chartOnly.chart_clarity_confidence, 1)}</span></div>
                      {chartOnly.thesis && <p className="hint" style={{ marginTop: 11 }}>{String(chartOnly.thesis)}</p>}
                      {asList(chartOnly.missing_evidence).length > 0 && (
                        <>
                          <div className="eyebrow" style={{ marginTop: 14 }}>Missing chart evidence</div>
                          {asList(chartOnly.missing_evidence).map((m: any, i: number) => (
                            <div className="kv" key={i}><span className="k">·</span><span className="v" style={{ color: "var(--warn)" }}>{String(m)}</span></div>
                          ))}
                        </>
                      )}
                      <p className="hint" style={{ marginTop: 11 }}>{String(chartOnly.caveat ?? "")}</p>
                    </div>
                  </div>

                  {/* VERIFIED BACKEND */}
                  <div className="panel">
                    <div className="panel-h">
                      <div><h3>Verified FIA evidence <span className="badge info">BACKEND</span></h3><p className="hint" style={{ marginTop: 1 }}>Nothing in this block comes from the uploaded image.</p></div>
                    </div>
                    <div className="panel-b">
                      <div className="recon">
                        <span className="k">8H</span><span className="v" style={{ color: dirColor(asObj(backend.horizon_8h).direction) }}>{pct(asObj(backend.horizon_8h).bullish_probability, 2)}</span>
                        <span className="k">CONF</span><span className="v">{pct(asObj(backend.horizon_8h).confidence, 2)}</span>
                        <span className="k">4H</span><span className="v" style={{ color: dirColor(asObj(backend.horizon_4h).direction) }}>{pct(asObj(backend.horizon_4h).bullish_probability, 2)}</span>
                        <span className="k">CONF</span><span className="v">{pct(asObj(backend.horizon_4h).confidence, 2)}</span>
                      </div>
                      {finite(asObj(backend.horizon_8h).no_information_tilt_points) !== null && (
                        <div className="tilt" style={{ marginTop: 11 }}>
                          <span className="k">BASE RATE</span>
                          <span className="v">
                            Raw evidence {pct(asObj(backend.horizon_8h).raw_probability, 2)}; the calibration intercept alone contributes{" "}
                            <b>{num(asObj(backend.horizon_8h).no_information_tilt_points, 2)} points</b>. That portion is an unconditional base rate,
                            not evidence about today.
                          </span>
                        </div>
                      )}
                      <div className="kv" style={{ marginTop: 11 }}><span className="k">Pre-move state</span><span className="v">{upper(words(backend.premove_state))}</span></div>
                      <div className="kv"><span className="k">Regime</span><span className="v">{upper(words(backend.regime))}</span></div>
                      <div className="kv"><span className="k">Catalyst risk</span><span className="v">{upper(words(asObj(backend.catalyst_risk).level))}{asObj(backend.catalyst_risk).known === false ? " · NOT FULLY KNOWN" : ""}</span></div>
                      <div className="kv"><span className="k">Evidence coverage</span><span className="v num">{num(asObj(backend.evidence_quality).coverage, 2)} · {words(asObj(backend.evidence_quality).grade)}</span></div>
                      <div className="kv"><span className="k">Missing sources</span><span className="v" style={{ color: asList(backend.missing_sources).length ? "var(--warn)" : undefined }}>{asList(backend.missing_sources).join(" · ") || "none"}</span></div>
                      <div className="kv"><span className="k">Bull / Bear strength</span><span className="v num">{num(asObj(backend.reasoning_layers).bull_strength, 3)} / {num(asObj(backend.reasoning_layers).bear_strength, 3)}</span></div>
                      <div className="kv"><span className="k">Critic severity</span><span className="v">{upper(words(asObj(backend.reasoning_layers).critic_severity))}</span></div>

                      {asList(backend.dominant_drivers).length > 0 && (
                        <>
                          <div className="eyebrow" style={{ marginTop: 14 }}>Dominant drivers by effective weight</div>
                          <div className="sx" style={{ marginTop: 8 }}>
                            <table className="grid">
                              <thead><tr><th>Driver</th><th>Score</th><th>Weight</th><th>Freshness</th></tr></thead>
                              <tbody>
                                {asList(backend.dominant_drivers).map((raw: any, i: number) => {
                                  const d = asObj(raw);
                                  const s = finite(d.score) ?? 0;
                                  return (
                                    <tr key={i}>
                                      <td>{String(d.name ?? "—")}</td>
                                      <td className="n" style={{ color: s > 0 ? "var(--bull)" : "var(--bear)" }}>{num(d.score, 3)}</td>
                                      <td className="n">{num(d.effective_weight, 3)}</td>
                                      <td>{upper(words(d.freshness))}</td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* RIGHT RAIL */}
                <div className="stack">
                  <div className="panel">
                    <div className="panel-h"><div><h3>Your analysis vs FIA</h3><p className="hint" style={{ marginTop: 1 }}>FIA does not simply agree with you.</p></div></div>
                    <div className="panel-b">
                      <div className="figs" style={{ marginTop: 0 }}>
                        <div className="fig sm"><span className="v num" style={{ color: "var(--t-hi)" }}>{upper(words(userCmp.verdict))}</span><span className="k">VERDICT</span></div>
                      </div>
                      <div className="kv" style={{ marginTop: 11 }}><span className="k">Your direction</span><span className="v" style={{ color: dirColor(userCmp.user_direction) }}>{upper(words(userCmp.user_direction))}</span></div>
                      <div className="kv"><span className="k">Vision direction</span><span className="v" style={{ color: dirColor(userCmp.chart_direction) }}>{upper(words(userCmp.chart_direction))}</span></div>
                      <div className="kv"><span className="k">FIA 8H direction</span><span className="v" style={{ color: dirColor(userCmp.fia_8h_direction) }}>{upper(words(userCmp.fia_8h_direction))}</span></div>
                      <div style={{ marginTop: 11 }}>
                        {asList(userCmp.reasons).map((r: any, i: number) => (
                          <p className="hint" key={i} style={{ marginTop: 5 }}>· {String(r)}</p>
                        ))}
                      </div>
                      {asList(userCmp.user_claims_not_confirmed).length > 0 && (
                        <>
                          <div className="eyebrow" style={{ marginTop: 14 }}>Your claims not confirmed by vision</div>
                          {asList(userCmp.user_claims_not_confirmed).map((c: any, i: number) => (
                            <div className="cl-warnline" key={i}>! {words(c)}</div>
                          ))}
                        </>
                      )}
                      {asList(userCmp.confirmed_by_user_and_vision).length > 0 && (
                        <>
                          <div className="eyebrow" style={{ marginTop: 14 }}>Confirmed by you and vision</div>
                          {asList(userCmp.confirmed_by_user_and_vision).map((c: any, i: number) => (
                            <div className="cl-line" key={i}>✓ {words(c)}</div>
                          ))}
                        </>
                      )}
                      <p className="indep" style={{ marginTop: 11 }}>{String(userCmp.policy ?? "")}</p>
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panel-h"><div><h3>Separation policy</h3><p className="hint" style={{ marginTop: 1 }}>What this report refuses to do.</p></div></div>
                    <div className="panel-b">
                      {Object.entries(asObj(report?.separation_policy)).map(([k, v]) => (
                        <div className="kv" key={k}>
                          <span className="k">{k.replace(/_/g, " ")}</span>
                          <span className="v" style={{ color: v === false ? "var(--bull)" : "var(--t-mid)" }}>{String(v).toUpperCase()}</span>
                        </div>
                      ))}
                      <div className="kv"><span className="k">Vision provider</span><span className="v">{words(chartOnly.provider)}</span></div>
                      <div className="kv"><span className="k">Vision model</span><span className="v num" style={{ fontSize: 10 }}>{words(chartOnly.model)}</span></div>
                    </div>
                  </div>

                  {backendErrors.length > 0 && (
                    <div className="panel">
                      <div className="panel-h"><div><h3>Backend evidence gaps</h3><p className="hint" style={{ marginTop: 1 }}>Surfaced, not swallowed.</p></div><span className="badge bad">{backendErrors.length}</span></div>
                      <div className="panel-b">
                        {backendErrors.map((e: any, i: number) => (
                          <p className="hint" key={i} style={{ color: "var(--warn)", marginTop: 5 }}>· {String(e)}</p>
                        ))}
                        <p className="hint" style={{ marginTop: 9 }}>
                          Where backend evidence failed, the comparison above reports INSUFFICIENT DATA rather than
                          treating the gap as neutral agreement.
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="panel">
                    <div className="panel-h"><div><h3>Setup quality basis</h3></div></div>
                    <div className="panel-b">
                      <div className="kv"><span className="k">Grade</span><span className="v">{upper(words(setup.grade))}</span></div>
                      <div className="kv"><span className="k">Agreement</span><span className="v">{upper(words(asObj(setup.basis).agreement))}</span></div>
                      <div className="kv"><span className="k">Chart features detected</span><span className="v num">{asObj(setup.basis).chart_features_detected ?? "—"}</span></div>
                      <div className="kv"><span className="k">Backend degraded</span><span className="v">{String(asObj(setup.basis).backend_evidence_degraded).toUpperCase()}</span></div>
                      <div className="kv"><span className="k">Is a probability</span><span className="v" style={{ color: "var(--bull)" }}>FALSE</span></div>
                      <div className="kv"><span className="k">Is a win rate</span><span className="v" style={{ color: "var(--bull)" }}>FALSE</span></div>
                      <div className="kv"><span className="k">Validation gate</span><span className="v">{words(setup.validation_gate)}</span></div>
                      <p className="hint" style={{ marginTop: 10 }}>{String(setup.note ?? "")}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="footnote">
                <span className="k">Note</span>
                <span className="hint">{String(report?.note ?? "")}</span>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
