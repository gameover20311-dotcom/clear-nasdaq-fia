"use client";

/* CLEAR NASDAQ — OBSIDIAN WIDE COCKPIT
 *
 * Bound to the real atomic dashboard payload (/api/fia/dashboard ->
 * backend /api/final/dashboard). Every value rendered here comes from a real
 * backend field.
 *
 * TRUTH RULES ENFORCED IN THIS COMPONENT
 *   - null/undefined renders as an em dash or an explicit MISSING state.
 *     It is NEVER rendered as 0, 50 or "neutral".
 *   - 4H and 8H are read from separate fields and are never blended.
 *   - NO_EDGE, DEGRADED, STALE and MISSING_DATA are first-class visible states.
 *   - Forward-OOS sample size is printed exactly as reported.
 *   - The calibration base-rate tilt is shown next to the published probability
 *     because a large share of that number can be unconditional base rate.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Obj = Record<string, any>;

const API = "/api/fia/dashboard";
const REFRESH_MS = 60_000;

/* ------------------------------------------------------------------ utils */
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
  return n === null ? "—" : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
};
const signed = (v: any, d = 2) => {
  const n = finite(v);
  return n === null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(d)}`;
};
const words = (v: any) => {
  if (v && typeof v === "object") {
    const o = v as Obj;
    return String(o.level ?? o.status ?? o.state ?? o.message ?? "—").replace(/_/g, " ");
  }
  return String(v ?? "—").replace(/_/g, " ");
};
const upper = (v: any) => String(v ?? "").toUpperCase();

const HEALTHY = ["LIVE", "OK", "PASS", "READY", "HEALTHY", "AVAILABLE", "LIVE_SCORED"];
const BAD = ["ERROR", "FAILED", "FAIL", "UNAVAILABLE", "MISSING", "DOWN", "DEAD"];
const WARNISH = ["STALE", "DELAYED", "DEGRADED", "AGING", "FALLBACK"];
const tone = (v: any): "good" | "bad" | "mid" => {
  const s = upper(v);
  if (HEALTHY.includes(s)) return "good";
  if (BAD.includes(s)) return "bad";
  if (WARNISH.includes(s)) return "mid";
  return "mid";
};
const ageText = (d: Date | null) => {
  if (!d) return "waiting";
  const s = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`;
};
const hhmmss = (v: any) => {
  if (!v) return "—";
  const d = new Date(String(v));
  return Number.isNaN(d.getTime()) ? String(v) : d.toISOString().slice(11, 19) + "Z";
};
const shortHash = (v: any, head = 8, tail = 6) => {
  const s = String(v ?? "");
  return s.length > head + tail + 3 ? `${s.slice(0, head)}…${s.slice(-tail)}` : s || "—";
};
const dirColor = (d: any) =>
  upper(d) === "BULLISH" ? "var(--bull)" : upper(d) === "BEARISH" ? "var(--bear)" : "var(--t-mid)";

/* ------------------------------------------------------------- components */
function Badge({ value, kind }: { value: any; kind?: "good" | "bad" | "mid" | "neutral" | "info" }) {
  const k = kind ?? tone(value);
  return <span className={`badge ${k}`}>{upper(words(value))}</span>;
}
function KV({ k, v, color }: { k: string; v: any; color?: string }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span className="v" style={color ? { color } : undefined}>{v}</span>
    </div>
  );
}

/* ================================================================= page */
export default function Cockpit() {
  const [page, setPage] = useState<"overview" | "intelligence" | "validation">("overview");
  const [payload, setPayload] = useState<Obj | null>(null);
  const [session, setSession] = useState<Obj | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [receivedAt, setReceivedAt] = useState<Date | null>(null);
  const [, setClock] = useState(Date.now());
  const [openAcc, setOpenAcc] = useState<Record<string, boolean>>({ brains: true });
  const inFlight = useRef(false);

  const loadSession = useCallback(async () => {
    const r = await fetch("/api/auth/session", { cache: "no-store" }).catch(() => null);
    if (!r) return;
    if (r.status === 401) { window.location.assign("/login"); return; }
    const b = await r.json().catch(() => ({}));
    if (r.ok && b?.ok === true) setSession(asObj(b.user));
  }, []);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const r = await fetch(API, { cache: "no-store", headers: { "cache-control": "no-cache" } });
      if (r.status === 401) { window.location.assign("/login"); return; }
      const b = await r.json().catch(() => ({}));
      if (!r.ok || b?.ok !== true) throw new Error(b?.detail || b?.error || `HTTP ${r.status}`);
      setPayload(b);
      setReceivedAt(new Date());
      setError("");
    } catch (e: any) {
      // Fail closed: the stale snapshot is dropped rather than shown as current.
      setPayload(null);
      setError(e?.message || "FIA dashboard unavailable");
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSession(); load(); }, [load, loadSession]);
  useEffect(() => {
    const id = window.setInterval(() => {
      setClock(Date.now());
      if (document.visibilityState === "visible" && receivedAt && Date.now() - receivedAt.getTime() >= REFRESH_MS) load();
    }, 1000);
    return () => window.clearInterval(id);
  }, [load, receivedAt]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    window.location.assign("/login");
  }
  const toggle = (id: string) => setOpenAcc((s) => ({ ...s, [id]: !s[id] }));

  /* ------------------------------------------------------- derived data */
  const live = asObj(payload?.live);
  const snapshot = asObj(live.snapshot);
  const data = asObj(snapshot.data && typeof snapshot.data === "object" ? snapshot.data : snapshot);
  const forecast = asObj(live.forecast);
  const cognitive = asObj(live.cognitive);
  const premove = asObj(live.premove_watch);
  const horizons = asObj(premove.horizons);
  const h8 = asObj(horizons["8h"]);
  const h4 = asObj(horizons["4h"]);
  const quality = asObj(premove.evidence_quality);
  const catalyst = asObj(premove.catalyst_risk);
  const shift = asObj(premove.probability_shift);
  const thresholds = asObj(premove.thresholds);
  const perf = asObj(premove.measured_performance_disclosure);
  const provider = asObj(data.provider_health);
  const sourceHealth = asObj(data.source_health);
  const critic = asObj(cognitive.critic);
  const hypotheses = asObj(cognitive.hypotheses);
  const analogy = asObj(cognitive.historical_analogy);
  const calibration = asObj(cognitive.calibration);
  const interval = asObj(cognitive.probability_interval_approx_95);
  const evidenceLedger = asObj(cognitive.evidence_ledger);
  const drift = asObj(cognitive.drift_monitor);
  const news = asObj(cognitive.news_intelligence);
  const cogRegime = asObj(cognitive.regime);
  const fusion = asObj(cognitive.fusion);
  const specialists = asList(cognitive.specialists);
  const missingEvidence = asList(cognitive.missing_evidence);
  const backtest = asObj(payload?.backtest);
  const finalCockpit = asObj(payload?.final_cockpit);
  const dataTruth = asObj(payload?.data_truth);
  const brain = asObj(payload?.brain_v66);
  const whole = asObj(payload?.whole_system_backtest);
  const forward = asObj(whole.live_forward_oos);
  const phase25 = asObj(payload?.phase25);
  const mega = asObj(data.mega_cap_details);
  const nqGroup = asObj(asObj(live.liquidity_groups).nq);
  const nqLevels = asObj(nqGroup.levels);

  const h8cal = asObj(h8.calibration);
  const h4cal = asObj(h4.calibration);
  const drivers8 = asList(h8.drivers);
  const state = upper(premove.state || "UNAVAILABLE");
  const stateDir = upper(h8.direction || forecast.direction || "UNKNOWN");
  const directional = ["BULLISH", "BEARISH"].includes(stateDir);
  const noEdge = ["NO_EDGE", "NEUTRAL"].includes(stateDir) || state === "NO_EDGE";

  const megaRows = useMemo(
    () =>
      Object.entries(mega)
        .map(([symbol, raw]) => ({ symbol, ...asObj(raw) }))
        .sort((a: any, b: any) => (finite(b.weight) || 0) - (finite(a.weight) || 0)),
    [mega]
  );
  const levelRows = useMemo(
    () =>
      Object.entries(nqLevels)
        .map(([key, raw]) => ({ key, ...asObj(raw) }))
        .filter((x: any) => finite(x.price) !== null)
        .sort((a: any, b: any) => (finite(b.price) || 0) - (finite(a.price) || 0)),
    [nqLevels]
  );
  const sortedDrivers = useMemo(
    () => [...drivers8].sort((a, b) => Math.abs(finite(asObj(b).effective_weight) || 0) - Math.abs(finite(asObj(a).effective_weight) || 0)),
    [drivers8]
  );

  const missingSources = asList(provider.missing_sources);
  const staleSources = asList(provider.stale_sources).length
    ? asList(provider.stale_sources)
    : Object.entries(sourceHealth).filter(([, v]) => upper(asObj(v).status) === "DELAYED").map(([k]) => k);
  const criticalMissing = asList(provider.critical_missing);

  const bull8 = finite(h8.bullish_probability);
  const bear8 = finite(h8.bearish_probability);
  const bull4 = finite(h4.bullish_probability);

  const Acc = ({ id, idx, title, sub, right, children }: any) => (
    <div className={`acc-i ${openAcc[id] ? "open" : ""}`} id={`acc-${id}`}>
      <button className="acc-b" onClick={() => toggle(id)}>
        <span className="acc-x">{idx}</span>
        <span><span className="acc-t">{title}</span><span className="acc-s">{sub}</span></span>
        <span className="acc-r">{right}<span className="chev" /></span>
      </button>
      <div className="acc-body">{children}</div>
    </div>
  );

  /* ------------------------------------------------------------- render */
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <div className="brand-mark"><span className="brand-dot" /><span className="brand-name">CLEAR NASDAQ</span></div>
          <div className="brand-sub">OBSIDIAN · NQ PRE-MOVE INTELLIGENCE</div>
        </div>
        <nav className="nav" aria-label="Primary">
          {([
            ["overview", "01", "Overview", "What is FIA seeing"],
            ["intelligence", "02", "Intelligence", "Why it sees it"],
            ["validation", "03", "Validation", "Has it earned trust"],
          ] as const).map(([id, idx, lbl, sub]) => (
            <button key={id} className="nav-item" aria-current={page === id ? "page" : undefined} onClick={() => { setPage(id as any); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
              <span className="idx">{idx}</span><span className="lbl">{lbl}</span><span className="sub">{sub}</span>
            </button>
          ))}
          <div className="nav-div">Tools</div>
          <Link href="/chart-lab" className="nav-item" style={{ textDecoration: "none" }}>
            <span className="idx">↗</span><span className="lbl">Chart Lab</span><span className="sub">Upload · vision · confluence</span>
          </Link>
          <Link href="/whole-system-backtest" className="nav-item" style={{ textDecoration: "none" }}>
            <span className="idx">↗</span><span className="lbl">Backtest</span><span className="sub">Whole-system validation</span>
          </Link>
          {/* Phase 33 / Phase 34 are deliberately NOT in trader navigation.
              Phase 33 was validated on 78 untouched holdout rows and LOST to BASE_FIA
              (4H 37.33% vs 53.33%, 8H 38.71% vs 48.39%); its own gate reports
              calibration_approved_for_live_probability: false.
              Phase 34 has 1 of 13 data sources available and its replay is
              BLOCKED_BY_MISSING_HISTORICAL_INSTITUTIONAL_INPUTS — never validated.
              Both remain reachable directly at /phase33 and /phase34 for research.
              Research scaffolding must not be presented as production intelligence. */}
        </nav>
        <div className="rail-foot"><p className="hint">Research intelligence cockpit. Not a trading signal, not an order-entry surface.</p></div>
      </aside>

      <div className="main">
        <div className="topbar">
          <span className="tb">
            <span className={`dot ${error ? "bad" : criticalMissing.length ? "bad" : missingSources.length || staleSources.length ? "warn" : "ok"}`} />
            <span className="tb-k">Data</span>
            <span className="tb-v">
              {error ? "UNAVAILABLE" : `${upper(provider.overall || snapshot.status || "UNKNOWN")}${missingSources.length ? ` · ${missingSources.length} missing` : ""}`}
            </span>
          </span>
          <span className="tb-sep" />
          <span className="tb"><span className="tb-k">Coverage</span><span className="tb-v num">{finite(forecast.data_coverage) === null ? "—" : num(forecast.data_coverage, 3)}</span></span>
          <span className="tb-sp" />
          <span className="tb"><span className="tb-k">Updated</span><span className="tb-v num">{hhmmss(payload?.data_as_of || payload?.generated_at)}</span></span>
          <span className="tb-sep" />
          <span className="tb">
            <span className={`dot ${premove.forecast_id ? "ok" : "warn"}`} />
            <span className="tb-k">Forecast</span>
            <span className="tb-v">{premove.forecast_id ? `LOCKED · seq ${asObj(premove.ledger).seq ?? "—"}` : "NOT LOCKED"}</span>
          </span>
          <span className="tb-sep" />
          <button className="ghost-btn" onClick={logout} style={{ fontFamily: "var(--mono)", fontSize: 9, letterSpacing: ".09em", color: "var(--t-low)", border: "1px solid var(--line)", padding: "4px 8px", borderRadius: "var(--r)" }}>
            {session?.display_name ? `${session.display_name} · LOGOUT` : "LOGOUT"}
          </button>
        </div>

        {error && (
          <div style={{ margin: "12px 24px 0", padding: "11px 13px", border: "1px solid var(--bear-br)", background: "var(--bear-bg)", borderRadius: "var(--r-lg)", color: "var(--bear)", fontSize: 11.5 }}>
            <b>FIA live snapshot failed.</b> <span style={{ color: "var(--t-mid)" }}>{error}</span>
            <div className="hint" style={{ marginTop: 6 }}>The previous snapshot was discarded rather than shown as current. No values are displayed from a failed fetch.</div>
          </div>
        )}

        {/* ============================================ PAGE 01 · COCKPIT */}
        <section className={`page ${page === "overview" ? "active" : ""}`}>
          <div className="page-head">
            <div>
              <h1 className="page-title">Pre-Move Cockpit</h1>
              <p className="page-desc">Decision context only. Reasoning on Intelligence, system proof on Validation.</p>
            </div>
          </div>

          <div className="state-row four">
            <div className="state-cell">
              <div className="sc-b">
                <div className="sc-k">Market Regime</div>
                <div className="sc-v">
                  <span className="sc-n">{upper(words(premove.regime || forecast.regime || "UNKNOWN"))}</span>
                  {cogRegime.primary && <span className="badge neutral">{upper(words(cogRegime.primary))}</span>}
                </div>
                <div className="sc-note">
                  {asList(cogRegime.secondary).length
                    ? `Cognitive: ${asList(cogRegime.secondary).map(words).join(" · ")} · confidence ${num(cogRegime.confidence, 3)}`
                    : "Cognitive regime unavailable"}
                </div>
              </div>
            </div>
            <div className="state-cell">
              <div className="sc-b">
                <div className="sc-k">Catalyst Risk</div>
                <div className="sc-v">
                  <span className="sc-n" style={{ color: upper(catalyst.level) === "LOW" ? "var(--bull)" : "var(--warn)" }}>{upper(words(catalyst.level || "UNKNOWN"))}</span>
                  {catalyst.known === false && <span className="badge mid">NOT FULLY KNOWN</span>}
                  {catalyst.macro_high_impact == null && <span className="badge mid">CALENDAR MISSING</span>}
                </div>
                <div className="sc-note">
                  {catalyst.earnings_catalyst_risk === true ? "Earnings catalyst active." : "No earnings catalyst."}{" "}
                  {catalyst.macro_high_impact == null && "Macro calendar has no source — this reading is incomplete."}
                </div>
              </div>
            </div>
            <div className="state-cell tap" role="button" tabIndex={0} onClick={() => setPage("validation")}>
              <div className="sc-b">
                <div className="sc-k">Evidence Quality</div>
                <div className="sc-v">
                  <span className="sc-n">{upper(words(quality.grade || "UNKNOWN"))}</span>
                  <span className={`badge ${quality.degraded || quality.stale ? "mid" : "good"} num`}>COV {finite(quality.coverage) === null ? "—" : num(quality.coverage, 2)}</span>
                </div>
                <div className="sc-note">
                  {finite(quality.live_signal_count) !== null ? `${quality.live_signal_count} of ${quality.total_signal_count} signals live` : "signal counts unavailable"}
                  {missingEvidence.length ? ` · ${missingEvidence.length} specialists missing` : ""}
                </div>
              </div>
              <span className="cue">System →</span>
            </div>
            <div className="state-cell tap" role="button" tabIndex={0} onClick={() => setPage("validation")}>
              <div className="sc-b">
                <div className="sc-k">Measured Performance</div>
                <div className="sc-v">
                  <span className="sc-n" style={{ color: upper(perf.status) === "NO_DEMONSTRATED_EDGE" ? "var(--bear)" : "var(--t-mid)" }}>
                    {perf.status ? upper(words(perf.status)) : "—"}
                  </span>
                  <span className="badge bad">NOT PROVEN</span>
                </div>
                <div className="sc-note">
                  {finite(perf.historical_4h_accuracy_pct) !== null
                    ? `Historical 4H ${pct(perf.historical_4h_accuracy_pct, 2)} · 8H ${pct(perf.historical_8h_accuracy_pct, 2)}`
                    : "Historical accuracy unavailable"} · Forward-OOS n = {asObj(forward["4h"]).n ?? 0}
                </div>
              </div>
              <span className="cue">Evidence →</span>
            </div>
          </div>

          <div className="cockpit">
            <div className="stack">
              {/* HERO */}
              <div className="hero">
                <div className="hero-in">
                  <div className="hero-top">
                    <div>
                      <div className="eyebrow" style={{ marginBottom: 8 }}>Pre-Move Status</div>
                      <div className="chip" style={{ borderColor: noEdge ? "var(--warn-br)" : directional ? (stateDir === "BULLISH" ? "var(--bull-br)" : "var(--bear-br)") : "var(--line-hi)", background: noEdge ? "var(--warn-bg)" : stateDir === "BEARISH" ? "var(--bear-bg)" : "var(--bull-bg)" }}>
                        <span className="dot" style={{ background: noEdge ? "var(--warn)" : dirColor(stateDir) }} />
                        <span className="txt" style={{ color: noEdge ? "var(--warn)" : dirColor(stateDir) }}>
                          {state}{directional ? ` · ${stateDir}` : noEdge ? " · NO EDGE" : ""}
                        </span>
                      </div>
                      {state === "WATCH" && (
                        <div className="unconf"><span className="k">WATCH</span><span className="v">Not confirmed — evidence leans {stateDir.toLowerCase()}, conviction is not established</span></div>
                      )}
                    </div>
                  </div>

                  {forecast.thesis && <p className="thesis">{String(forecast.thesis)}</p>}

                  {(missingEvidence.length > 0 || staleSources.length > 0) && (
                    <div className="degraded">
                      <span className="k">DEGRADED</span>
                      <span className="v">
                        {missingEvidence.length > 0 && <>{missingEvidence.length} specialist{missingEvidence.length === 1 ? "" : "s"} returned MISSING: {missingEvidence.map((m: any) => asObj(m).name).filter(Boolean).join(", ")}. </>}
                        {staleSources.length > 0 && <>Delayed sources: {staleSources.join(", ")}. </>}
                        Missing inputs carry weight factor 0.00 — they are not scored as neutral.
                      </span>
                    </div>
                  )}

                  {/* 8H PRIMARY */}
                  <div className="prob">
                    <div className="prob-h">
                      <div className="prob-l">
                        <span className="prob-t">8H DISTRIBUTION</span>
                        <span className="prob-tag">PRIMARY</span>
                        <Badge value={h8.state || "UNKNOWN"} kind={upper(h8.state) === "WATCH" ? "mid" : tone(h8.state)} />
                      </div>
                    </div>
                    <div className="figs">
                      <div className="fig bull"><span className="v num">{bull8 === null ? "—" : bull8.toFixed(2)}<span style={{ fontSize: ".4em" }}>%</span></span><span className="k">BULLISH</span></div>
                      <div className="fig bear"><span className="v num">{bear8 === null ? "—" : bear8.toFixed(2)}<span style={{ fontSize: ".4em" }}>%</span></span><span className="k">BEARISH</span></div>
                      <div className="fig sm" style={{ marginLeft: "auto" }}>
                        <span className="v num" style={{ color: (finite(h8.confidence) ?? 0) < 20 ? "var(--warn)" : "var(--t-hi)" }}>{pct(h8.confidence, 2)}</span>
                        <span className="k">CONFIDENCE</span>
                      </div>
                    </div>
                    <div className="field">
                      <div className="track">
                        <div className="track-bull" style={{ width: `${bull8 === null ? 0 : Math.max(0, Math.min(100, bull8))}%` }} />
                        <i style={{ left: "25%" }} /><i style={{ left: "75%" }} /><span className="mid" style={{ left: "50%" }} />
                      </div>
                      <div className="scale"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>
                    </div>

                    {finite(h8.raw_probability) !== null && (
                      <>
                        <div className="ladder">
                          <div className="lg"><span>Raw evidence</span><b>{pct(h8.raw_probability, 2)}</b></div>
                          <div className="ar">→</div>
                          <div className="lg warnv"><span>Base-rate tilt</span><b>{finite(h8cal.no_information_tilt_points) === null ? "—" : signed(h8cal.no_information_tilt_points, 2)}</b></div>
                          <div className="ar">→</div>
                          <div className="lg"><span>Published</span><b style={{ color: "var(--bull)" }}>{pct(bull8, 2)}</b></div>
                          {finite(interval.low) !== null && (
                            <div className="lg" style={{ marginLeft: "auto" }}><span>95% interval</span><b style={{ color: "var(--t-low)", fontSize: 11 }}>{num(interval.low, 2)} – {num(interval.high, 2)}</b></div>
                          )}
                        </div>
                        {finite(h8cal.no_information_tilt_points) !== null && (
                          <div className="tilt">
                            <span className="k">READ THIS FIRST</span>
                            <span className="v">
                              Raw evidence probability is <b>{pct(h8.raw_probability, 2)}</b>. Calibration moved it to {pct(bull8, 2)}, and the fitted
                              intercept alone contributes <b>{signed(h8cal.no_information_tilt_points, 2)} points</b>. That portion is an unconditional
                              base rate, <b>not evidence about today</b>. Confidence is {pct(h8.confidence, 2)}.
                            </span>
                          </div>
                        )}
                      </>
                    )}

                    {/* 4H SECONDARY */}
                    <div className="sub">
                      <div className="sub-l">
                        <div className="eyebrow">4H · Secondary</div>
                        <div className="sub-figs">
                          <span className="b num">{bull4 === null ? "—" : `${bull4.toFixed(2)}%`}</span>
                          <span className="r num">{finite(h4.bearish_probability) === null ? "—" : `${finite(h4.bearish_probability)!.toFixed(2)}%`}</span>
                        </div>
                      </div>
                      <div className="mini"><i style={{ width: `${bull4 === null ? 0 : Math.max(0, Math.min(100, bull4))}%` }} /></div>
                      <div style={{ textAlign: "right", flex: "none" }}>
                        <div className="eyebrow">Conf</div>
                        <span className="num" style={{ fontSize: ".95rem", fontWeight: 600, color: (finite(h4.confidence) ?? 0) < 20 ? "var(--warn)" : "var(--t-hi)" }}>{pct(h4.confidence, 2)}</span>
                      </div>
                      <div style={{ textAlign: "right", flex: "none" }}>
                        <div className="eyebrow">Raw → tilt</div>
                        <span className="num" style={{ fontSize: ".95rem", fontWeight: 600 }}>
                          {finite(h4.raw_probability) === null ? "—" : num(h4.raw_probability, 2)}{" "}
                          <span style={{ color: "var(--warn)" }}>{finite(h4cal.no_information_tilt_points) === null ? "" : signed(h4cal.no_information_tilt_points, 2)}</span>
                        </span>
                      </div>
                    </div>
                    <div className="bandnote">
                      4H and 8H are computed and published separately and are never blended. Direction follows the raw evidence score — calibration is not permitted to decide the sign
                      {h8.calibration_flips_direction === false ? " (calibration_flips_direction: false)." : "."}
                    </div>
                  </div>
                </div>
              </div>

              {/* DRIVERS */}
              {sortedDrivers.length > 0 && (
                <div>
                  <div className="panel-h" style={{ border: 0, padding: "0 0 9px" }}>
                    <div>
                      <h3 style={{ fontSize: 12 }}>Top Drivers · 8H · by effective weight</h3>
                      <p className="hint" style={{ marginTop: 1 }}>Engine weights, not a display ranking. Strongest score ≠ strongest driver.</p>
                    </div>
                  </div>
                  <div className="drivers">
                    {sortedDrivers.slice(0, 3).map((raw: any, i: number) => {
                      const d = asObj(raw);
                      const score = finite(d.score) ?? 0;
                      const w = finite(d.effective_weight) ?? 0;
                      const maxW = Math.abs(finite(asObj(sortedDrivers[0]).effective_weight) || 1) || 1;
                      const opposes = (score < 0 && stateDir === "BULLISH") || (score > 0 && stateDir === "BEARISH");
                      return (
                        <div key={i} className={`drv ${score > 0 ? "pos" : score < 0 ? "neg" : "mix"} ${opposes ? "conflict" : ""}`}>
                          <div className="drv-h">
                            <span className="drv-n">{String(d.name ?? "—").toUpperCase()} <span>{score > 0 ? "↑" : score < 0 ? "↓" : "→"}</span></span>
                            {opposes ? <span className="drv-flag">Opposes direction</span> : <span className={`badge ${score > 0 ? "good" : "bad"}`}>{signed(score, 3)}</span>}
                          </div>
                          <p className="drv-why">
                            {opposes
                              ? `Weight ${num(w, 3)} — this driver argues against the published ${stateDir.toLowerCase()} direction.`
                              : `Score ${signed(score, 3)} at effective weight ${num(w, 3)}.`}
                          </p>
                          <div className="drv-w">
                            <div className="drv-wt"><i style={{ width: `${Math.min(100, (Math.abs(w) / maxW) * 100)}%` }} /></div>
                            <span className="drv-wv">w {num(w, 3)}</span>
                          </div>
                          <div className="drv-f">
                            <span className="drv-src">{words(d.freshness).toUpperCase()}</span>
                            <Badge value={d.freshness} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* SUPPORTING vs AGAINST */}
              <div className="panel">
                <div className="panel-h">
                  <div><h3>Supporting vs Against</h3><p className="hint" style={{ marginTop: 1 }}>Disagreement is shown, not resolved away.</p></div>
                  {finite(h8.supporting_signal_count) !== null && <span className="badge neutral num">{h8.supporting_signal_count} SUPPORTING SIGNALS</span>}
                </div>
                <div className="ledger">
                  <div className="lcol">
                    <div className="lh for"><span className="t">Supporting</span><span className="n">{asList(forecast.bullish_evidence).length}</span></div>
                    {asList(forecast.bullish_evidence).length ? asList(forecast.bullish_evidence).slice(0, 5).map((e: any, i: number) => (
                      <div className="ev for" key={i}><span className="ev-w" /><div><p className="ev-t">{String(e)}</p></div></div>
                    )) : <p className="hint">No supporting evidence returned.</p>}
                  </div>
                  <div className="lrule" />
                  <div className="lcol">
                    <div className="lh ag"><span className="t">Against</span><span className="n">{asList(forecast.bearish_evidence).length}</span></div>
                    {asList(forecast.bearish_evidence).length ? asList(forecast.bearish_evidence).slice(0, 5).map((e: any, i: number) => (
                      <div className="ev ag" key={i}><span className="ev-w" /><div><p className="ev-t">{String(e)}</p></div></div>
                    )) : <p className="hint">No contradicting evidence returned.</p>}
                  </div>
                </div>
              </div>

              {/* INVALIDATION */}
              {asList(premove.invalidation).length > 0 && (
                <div className="panel inv">
                  <div className="panel-h"><span className="inv-q">WHAT WOULD CHANGE THIS VIEW?</span><span className="badge neutral">LOCKED WITH FORECAST</span></div>
                  <div className="panel-b">
                    <p className="inv-b">Published with the forecast and sealed alongside it, so the conditions cannot be rewritten after the fact to fit an outcome.</p>
                    <div className="inv-l">
                      {asList(premove.invalidation).map((c: any, i: number) => (
                        <div className="inv-i" key={i}><span className="inv-x num">{String(i + 1).padStart(2, "0")}</span><p className="inv-t">{String(c)}</p></div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* RIGHT RAIL */}
            <div className="stack">
              <div className="panel">
                <div className="panel-h"><div><h3>Probability Shift</h3><p className="hint" style={{ marginTop: 1 }}>Strengthening, weakening or unchanged?</p></div></div>
                <div className="panel-b">
                  <div className="shift-v">
                    <span className="shift-n num" style={{ color: shift.detected ? "var(--bear)" : "var(--t-mid)" }}>
                      {finite(shift.h8_delta_points) === null ? "—" : signed(shift.h8_delta_points, 2)}
                    </span>
                    <span className="num" style={{ fontSize: 10, color: "var(--t-low)" }}>PTS · 8H</span>
                    <span className="shift-d" style={{ color: shift.detected ? "var(--bear)" : "var(--t-low)" }}>
                      {shift.detected ? "SHIFT DETECTED" : "NO MEANINGFUL SHIFT"}
                    </span>
                  </div>
                  <div className="shift-bar">
                    <div className="shift-fill" style={{
                      width: `${Math.max(0.6, Math.min(50, (Math.abs(finite(shift.h8_delta_points) ?? 0) / 20) * 50))}%`,
                      left: (finite(shift.h8_delta_points) ?? 0) > 0 ? "50%" : `${50 - Math.max(0.6, Math.min(50, (Math.abs(finite(shift.h8_delta_points) ?? 0) / 20) * 50))}%`,
                      background: shift.detected ? "var(--bear)" : "var(--t-dim)",
                    }} />
                  </div>
                  <div className="shift-sc"><span>−20</span><span>0</span><span>+20</span></div>
                  <div className="mat">
                    <span className="k">MATERIALITY</span>
                    <span className="v" style={{ color: shift.detected ? "var(--bear)" : "var(--t-low)" }}>
                      {shift.detected ? "MATERIAL · ALERTED" : "BELOW THRESHOLD · NOT ALERTED"}
                    </span>
                  </div>
                  <p className="shift-desc">
                    4H delta {finite(shift.h4_delta_points) === null ? "—" : signed(shift.h4_delta_points, 2)} pts.
                    {" "}Threshold is {num(thresholds.min_shift_points, 2)} points with {thresholds.hysteresis_observations ?? "—"} confirming observations.
                    {asList(shift.reasons).length ? ` Reason: ${asList(shift.reasons).join("; ")}.` : ""}
                  </p>
                </div>
              </div>

              <div className="panel tap" role="button" tabIndex={0} onClick={() => { setPage("intelligence"); setOpenAcc((s) => ({ ...s, brains: true })); }}>
                <div className="panel-h">
                  <div><h3>Reasoning Layers</h3><p className="hint" style={{ marginTop: 1 }}>Bull, Bear and Disconfirming Critic.</p></div>
                  <span className="cue">Reasoning →</span>
                </div>
                <div className="panel-b">
                  <div className="isolated"><span className="k">INDEPENDENT</span><span className="v">Hypotheses generated separately; the Critic never sees a preferred answer.</span></div>
                  <div className="brains" style={{ marginTop: 10 }}>
                    <div className="brain b"><div className="brain-h"><span className="brain-n">BULL</span></div><div className="brain-v num">{num(asObj(hypotheses.bullish_hypothesis).strength, 2)}</div><p className="brain-c">Hypothesis strength.</p></div>
                    <div className="brain r"><div className="brain-h"><span className="brain-n">BEAR</span></div><div className="brain-v num">{num(asObj(hypotheses.bearish_hypothesis).strength, 2)}</div><p className="brain-c">Hypothesis strength.</p></div>
                    <div className="brain c"><div className="brain-h"><span className="brain-n">CRITIC</span></div><div className="brain-v num">{upper(words(critic.severity || "—"))} {finite(critic.score) === null ? "" : num(critic.score, 2)}</div><p className="brain-c">{asList(critic.objections).length} objection(s).</p></div>
                  </div>
                  <div className="recon">
                    <span className="k">DOMINANT</span>
                    <span className="v" style={{ color: dirColor(hypotheses.dominant_hypothesis) }}>{upper(words(hypotheses.dominant_hypothesis || "—"))}</span>
                    {finite(critic.reliability_penalty) !== null && <span className="badge mid" style={{ marginLeft: "auto" }}>−{num(critic.reliability_penalty, 3)} RELIABILITY</span>}
                  </div>
                  <p className="indep">Same-model agreement is recorded as metadata only and is never counted as independent evidence. Independent evidence comes solely from distinct prediction-time source clusters.</p>
                </div>
              </div>

              <div className="panel">
                <div className="panel-h"><div><h3>Data Status</h3><p className="hint" style={{ marginTop: 1 }}>Fail-closed, at a glance.</p></div></div>
                <div className="panel-b">
                  <KV k="Provider health" v={<Badge value={provider.overall || "UNKNOWN"} />} />
                  <KV k="Provider score" v={<span className="num">{finite(provider.score) === null ? "—" : num(provider.score, 1)}</span>} />
                  <KV k="Data coverage" v={<span className="num">{num(forecast.data_coverage, 3)}</span>} />
                  <KV k="Intelligence coverage" v={<span className="num">{num(forecast.intelligence_coverage, 3)}</span>} />
                  <KV k="Critical missing" v={<span className="num">{criticalMissing.length}</span>} color={criticalMissing.length ? "var(--bear)" : "var(--bull)"} />
                  <KV k="Missing sources" v={missingSources.length ? missingSources.join(" · ") : "none"} color={missingSources.length ? "var(--warn)" : undefined} />
                  <KV k="Delayed sources" v={staleSources.length ? staleSources.join(" · ") : "none"} color={staleSources.length ? "var(--warn)" : undefined} />
                  <KV k="Decision gate" v={upper(words(cognitive.decision_gate || "—"))} />
                  <KV k="Reliability" v={`${upper(words(cognitive.reliability || "—"))} · ${num(cognitive.reliability_score, 3)}`} />
                  <KV k="Truth gate" v={finalCockpit.truth_ready === true ? "READY" : "NOT READY"} color={finalCockpit.truth_ready === true ? "var(--bull)" : "var(--warn)"} />
                </div>
              </div>
            </div>
          </div>

          <div className="footnote">
            <span className="k">Evidence hash</span><span className="v hash">{shortHash(premove.evidence_hash, 12, 8)}</span>
            <span className="tb-sp" />
            <span className="hint">{loading ? "Refreshing…" : `Last received ${ageText(receivedAt)}`} · Research only · Broker execution OFF</span>
          </div>
        </section>

        {/* ======================================= PAGE 02 · INTELLIGENCE */}
        <section className={`page ${page === "intelligence" ? "active" : ""}`}>
          <div className="page-head">
            <div><h1 className="page-title">Intelligence</h1><p className="page-desc">Why the cockpit reads the way it does. Contradictions preserved rather than resolved away.</p></div>
          </div>

          <div className="panel" style={{ marginBottom: 12 }}>
            <div className="panel-h">
              <h3>Reconciled Thesis</h3>
              {asList(critic.objections).length > 0 && <span className="badge mid">CRITIC: {asList(critic.objections).length} OBJECTIONS</span>}
            </div>
            <div className="panel-b">
              <p style={{ fontSize: 12.5, lineHeight: 1.6, maxWidth: "76ch", color: "var(--t-mid)" }}>{forecast.thesis ? String(forecast.thesis) : "Live thesis unavailable."}</p>
              <div className="recon" style={{ marginTop: 11 }}>
                <span className="k">8H</span><span className="v" style={{ color: dirColor(h8.direction) }}>{pct(bull8, 2)} / {pct(bear8, 2)}</span>
                <span className="k">4H</span><span className="v" style={{ color: dirColor(h4.direction) }}>{pct(bull4, 2)} / {pct(h4.bearish_probability, 2)}</span>
                {finite(interval.low) !== null && <><span className="k">95% INTERVAL</span><span className="v" style={{ color: "var(--warn)" }}>{num(interval.low, 2)} – {num(interval.high, 2)}</span></>}
                <span className="k" style={{ marginLeft: "auto" }}>GATE</span><span className="v">{upper(words(cognitive.decision_gate || "—"))}</span>
              </div>
              {cognitive.probability_interval_basis && <p className="hint" style={{ marginTop: 9 }}>Interval basis: {String(cognitive.probability_interval_basis).replace(/_/g, " ")}.</p>}
            </div>
          </div>

          <div className="acc">
            <Acc id="brains" idx="01" title="Reasoning Layers" sub="Bull, Bear and Disconfirming Critic"
              right={asList(critic.objections).length ? <span className="badge mid">OBJECTIONS</span> : <span className="badge good">CLEAR</span>}>
              <div className="isolated" style={{ marginTop: 12 }}>
                <span className="k">STRUCTURE</span>
                <span className="v">Hypotheses and Critic are live cognitive fields. The V7.4 Three-Brain is a separate package whose roles emit nine flat fields — it has <b style={{ color: "var(--warn)" }}>no cause, transmission, expected-effect or invalidation field</b>; that reasoning exists only as prose inside <span className="num">thesis</span>.</span>
              </div>
              <div className="bblock b">
                <div className="bblock-h"><span className="brain-n">BULL HYPOTHESIS</span><span className="badge good">STRENGTH {num(asObj(hypotheses.bullish_hypothesis).strength, 4)}</span></div>
                <div style={{ marginTop: 9 }}>
                  {asList(asObj(hypotheses.bullish_hypothesis).evidence).slice(0, 5).map((e: any, i: number) => (
                    <div className="kv" key={i}><span className="k">{asObj(e).specialist}</span><span className="v num">{signed(asObj(e).score, 4)} · rel {num(asObj(e).reliability, 2)}</span></div>
                  ))}
                </div>
              </div>
              <div className="bblock r">
                <div className="bblock-h"><span className="brain-n">BEAR HYPOTHESIS</span><span className="badge bad">STRENGTH {num(asObj(hypotheses.bearish_hypothesis).strength, 4)}</span></div>
                <div style={{ marginTop: 9 }}>
                  {asList(asObj(hypotheses.bearish_hypothesis).evidence).slice(0, 5).map((e: any, i: number) => (
                    <div className="kv" key={i}><span className="k">{asObj(e).specialist}</span><span className="v num">{signed(asObj(e).score, 4)} · rel {num(asObj(e).reliability, 2)}</span></div>
                  ))}
                </div>
              </div>
              <div className="bblock c">
                <div className="bblock-h"><span className="brain-n">DISCONFIRMING CRITIC</span><span className="badge mid">SEVERITY {upper(words(critic.severity))} · {num(critic.score, 2)}</span></div>
                <div style={{ marginTop: 9 }}>
                  {asList(critic.objections).map((o: any, i: number) => (
                    <div className="cn" style={{ gridTemplateColumns: "1fr" }} key={i}><span className="cn-v">· {String(o)}</span></div>
                  ))}
                </div>
                <KV k="Reliability penalty" v={<span className="num">−{num(critic.reliability_penalty, 3)}</span>} color="var(--warn)" />
                <KV k="Hard hold" v={critic.hard_hold ? "TRIGGERED" : "NOT TRIGGERED"} color={critic.hard_hold ? "var(--bear)" : "var(--bull)"} />
                <KV k="Flagged for reinvestigation" v={asList(critic.reinvestigate).join(" · ") || "none"} />
              </div>
              <p className="indep" style={{ marginTop: 10 }}>Neutral evidence: {asList(hypotheses.neutral_evidence).join(" · ") || "none"}. Same-model agreement is never counted as independent evidence.</p>
            </Acc>

            <Acc id="specialists" idx="02" title="Specialist Panel" sub="Every evidence model, including those that did not report"
              right={<span className={`badge ${missingEvidence.length ? "bad" : "good"}`}>{missingEvidence.length} MISSING</span>}>
              <div className="sx" style={{ marginTop: 11 }}>
                <table className="grid">
                  <thead><tr><th>Specialist</th><th>Family</th><th>Direction</th><th>Score</th><th>Reliability</th></tr></thead>
                  <tbody>
                    {specialists.map((raw: any, i: number) => {
                      const s = asObj(raw);
                      const missing = upper(s.direction) === "MISSING";
                      return (
                        <tr key={i}>
                          <td>{String(s.name ?? "—")}</td>
                          <td>{String(s.family ?? "—")}</td>
                          <td style={{ color: missing ? "var(--warn)" : dirColor(s.direction) }}>{upper(words(s.direction))}</td>
                          <td className="n">{missing ? "—" : signed(s.score, 4)}</td>
                          <td className="n">{num(s.reliability, 2)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="hint" style={{ marginTop: 11 }}>A missing signal is emitted as score 0.0 with freshness <span className="num">missing</span>, and the freshness ladder maps missing to weight factor <b style={{ color: "var(--t-hi)" }}>0.00</b> — that 0.0 carries no vote and is not a neutral 50%.</p>
            </Acc>

            <Acc id="fusion" idx="03" title="Fusion Weights & Contributions" sub="Exactly how the number was assembled" right={<span className="badge info">TRANSPARENT</span>}>
              <div className="sx" style={{ marginTop: 11 }}>
                <table className="grid">
                  <thead><tr><th>Specialist</th><th>Weight</th><th>Score</th><th>Reliability</th><th>Contribution</th></tr></thead>
                  <tbody>
                    {asList(fusion.contributions).slice(0, 12).map((raw: any, i: number) => {
                      const c = asObj(raw);
                      return (
                        <tr key={i}>
                          <td>{String(c.specialist ?? "—")}</td>
                          <td className="n">{num(c.weight, 4)}</td>
                          <td className="n" style={{ color: (finite(c.score) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(c.score, 4)}</td>
                          <td className="n">{num(c.reliability, 2)}</td>
                          <td className="n" style={{ color: (finite(c.contribution) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(c.contribution, 5)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <KV k="Specialist probability" v={<span className="num">{num(fusion.specialist_probability, 3)}</span>} />
              <KV k="Analogy weight" v={<span className="num">{num(fusion.analogy_weight, 4)}</span>} />
              <KV k="Raw fused probability" v={<span className="num">{num(fusion.raw_bullish_probability, 3)}</span>} />
              <KV k="Mapping" v={<span className="num" style={{ fontSize: 10 }}>{String(h8.mapping ?? "—")}</span>} />
              {fusion.policy && <p className="hint" style={{ marginTop: 11 }}>{String(fusion.policy)}</p>}
            </Acc>

            <Acc id="macro" idx="04" title="Macro · Rates · Fed" sub="Policy path, yields, inflation, jobs, growth"
              right={<span className="badge bad">STRUCTURALLY ABSENT</span>}>
              <div className="sx" style={{ marginTop: 11 }}>
                <table className="grid">
                  <thead><tr><th>Input</th><th>Reading</th><th>Source</th><th>State</th></tr></thead>
                  <tbody>
                    <tr><td>Fed funds rate</td><td className="n">{num(data.fed_funds_rate, 2)}</td><td>FRED</td><td>{finite(data.fed_funds_rate) === null ? <Badge value="MISSING" /> : <Badge value="AVAILABLE" />}</td></tr>
                    <tr><td>US10Y</td><td className="n">{num(data.us10y_value, 3)}</td><td>{String(data.us10y_source ?? "—")}</td><td><Badge value={asObj(sourceHealth.us10y).status || "UNKNOWN"} /></td></tr>
                    <tr><td>DXY</td><td className="n">{num(data.dxy_value, 3)}</td><td>{String(data.dxy_source ?? "—")}</td><td><Badge value={asObj(sourceHealth.dxy).status || "UNKNOWN"} /></td></tr>
                    <tr><td>VIX</td><td className="n">{num(data.vix_value, 2)}</td><td>{String(data.vix_source ?? "—")}</td><td><Badge value={asObj(sourceHealth.volatility).status || "UNKNOWN"} /></td></tr>
                    <tr><td>Macro aggregate</td><td className="n">{data.macro == null ? "—" : num(data.macro, 3)}</td><td>{words(data.macro_status)}</td><td><Badge value="MISSING" /></td></tr>
                    <tr><td>CPI / PCE / NFP / GDP</td><td className="n">—</td><td>Not wired to this route</td><td><span className="badge bad">NOT AVAILABLE</span></td></tr>
                    <tr><td>ISM</td><td className="n">—</td><td>No series configured</td><td><span className="badge bad">NOT IMPLEMENTED</span></td></tr>
                    <tr><td>Fed stance / communication</td><td className="n">—</td><td>No producer</td><td><span className="badge bad">NOT IMPLEMENTED</span></td></tr>
                  </tbody>
                </table>
              </div>
              <p className="hint" style={{ marginTop: 11 }}>The macro leg is <b style={{ color: "var(--t-hi)" }}>structurally absent rather than transient</b>: the aggregate macro signal is hardcoded unavailable and the event calendar has no producer. Nothing is estimated to fill the gap.</p>
            </Acc>

            <Acc id="bigtech" idx="05" title="Big Tech · Semiconductors · Earnings" sub="Index-weighted leadership, then the semi complex"
              right={<span className="badge neutral num">{megaRows.length} NAMES</span>}>
              <div className="sx" style={{ marginTop: 11 }}>
                <table className="grid">
                  <thead><tr><th>Symbol</th><th>Change</th><th>Signal</th><th>Index weight</th></tr></thead>
                  <tbody>
                    {megaRows.map((m: any) => (
                      <tr key={m.symbol}>
                        <td>{m.symbol}</td>
                        <td className="n" style={{ color: (finite(m.change_percent) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{finite(m.change_percent) === null ? "—" : `${signed(m.change_percent, 2)}%`}</td>
                        <td className="n" style={{ color: (finite(m.signal) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(m.signal, 3)}</td>
                        <td className="n">{num(m.weight, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <KV k="Aggregate mega-cap leadership" v={<span className="num" style={{ color: (finite(data.mega_cap) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(data.mega_cap, 3)}</span>} />
              <KV k="Semiconductor complex" v={<span className="num" style={{ color: (finite(data.semis) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(data.semis, 3)}</span>} />
              <KV k="Earnings & guidance" v={words(data.earnings_status)} color="var(--warn)" />
            </Acc>

            <Acc id="breadth" idx="06" title="Equal-Weight Participation" sub="Dispersion across the tracked large-cap basket — not market breadth"
              right={<span className="badge mid">{(finite(data.breadth) ?? 0) >= 0 ? "FLAT" : "NOT CONFIRMING"}</span>}>
              <KV k="Equal-weight participation" v={<span className="num">{signed(data.breadth, 4)}</span>} color="var(--warn)" />
              <KV k="NQ vs SPX confirmation" v={<span className="num">{signed(data.spx_confirmation, 4)}</span>} color={(finite(data.spx_confirmation) ?? 0) < 0 ? "var(--bear)" : "var(--bull)"} />
              <KV k="NQ structure" v={<span className="num">{signed(data.nq_structure, 4)}</span>} />
              <KV k="Structure basis" v={`${data.nq_structure_bars ?? "—"} completed bars · ${words(data.nq_structure_source)}`} />
              <p className="hint" style={{ marginTop: 11 }}>This factor is the <b style={{ color: "var(--t-hi)" }}>equal-weighted mean change of the 15 tracked large caps</b> — it is <b style={{ color: "var(--warn)" }}>not market breadth</b>: there is no advance/decline line and no wide-universe sample. Every Semiconductor and Mega-cap constituent is inside this same basket, so it measures equal-weight vs cap-weight dispersion, not participation across the market. The confirmation score is SPY&rsquo;s normalised change, not a computed divergence statistic.</p>
            </Acc>

            <Acc id="cross" idx="07" title="Cross-Market · QQQ · SPX · DXY" sub="Index confirmation and relative strength"
              right={<span className="badge neutral">{String(data.symbol ?? "—")}</span>}>
              <div className="sx" style={{ marginTop: 11 }}>
                <table className="grid">
                  <thead><tr><th>Market</th><th>Level</th><th>Move</th><th>State</th></tr></thead>
                  <tbody>
                    <tr><td>{String(data.symbol ?? "QQQ")}</td><td className="n">{num(data.price, 2)}</td><td className="n" style={{ color: (finite(data.change_percent) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(data.change_percent, 2)}%</td><td><Badge value={asObj(sourceHealth.market_quotes).status || "UNKNOWN"} /></td></tr>
                    <tr><td>SPX</td><td className="n">{num(data.spx_price, 2)}</td><td className="n" style={{ color: (finite(data.spx_change_percent) ?? 0) > 0 ? "var(--bull)" : "var(--bear)" }}>{signed(data.spx_change_percent, 2)}%</td><td><Badge value={asObj(sourceHealth.market_quotes).status || "UNKNOWN"} /></td></tr>
                    <tr><td>NQ</td><td className="n">{num(nqGroup.current_price, 2)}</td><td className="n">—</td><td><span className="badge good">LIQUIDITY LAYER</span></td></tr>
                    <tr><td>ES futures</td><td className="n">—</td><td className="n">—</td><td><span className="badge bad">NOT FETCHED</span></td></tr>
                    <tr><td>DXY</td><td className="n">{num(data.dxy_value, 3)}</td><td className="n">{signed(data.dxy_change_percent, 2)}%</td><td><Badge value={asObj(sourceHealth.dxy).status || "UNKNOWN"} /></td></tr>
                    <tr><td>VIX</td><td className="n">{num(data.vix_value, 2)}</td><td className="n">{signed(data.vix_change_percent, 2)}%</td><td><Badge value={asObj(sourceHealth.volatility).status || "UNKNOWN"} /></td></tr>
                  </tbody>
                </table>
              </div>
              <p className="hint" style={{ marginTop: 11 }}>ES is never fetched by the backend; SPX/SPY is the confirmation leg.</p>
            </Acc>

            <Acc id="catalyst" idx="08" title="Catalysts & Scheduled Events" sub="Verified events inside the window"
              right={<span className={`badge ${catalyst.known ? "mid" : "bad"}`}>{catalyst.known ? "INCOMPLETE" : "UNKNOWN"}</span>}>
              <KV k="Catalyst risk level" v={upper(words(catalyst.level))} color={upper(catalyst.level) === "LOW" ? "var(--bull)" : "var(--warn)"} />
              <KV k="High-impact macro in window" v={catalyst.macro_high_impact == null ? "UNKNOWN — SOURCE MISSING" : String(catalyst.macro_high_impact)} color="var(--warn)" />
              <KV k="Earnings catalyst risk" v={String(catalyst.earnings_catalyst_risk)} />
              <KV k="Tracked earnings events" v={<span className="num">{asList(asObj(live.upcoming_earnings).events).length}</span>} />
              <KV k="Fed speakers" v="NOT IMPLEMENTED" color="var(--warn)" />
              <p className="hint" style={{ marginTop: 11 }}>Catalyst risk may read LOW while the macro event calendar has no producer — that means &ldquo;nothing detected by the sources that answered&rdquo;, not &ldquo;nothing scheduled&rdquo;.</p>
            </Acc>

            <Acc id="liquidity" idx="09" title="Liquidity & Session Structure" sub="Asia · London · New York · HTF context"
              right={<span className="badge good num">{levelRows.length} LEVELS</span>}>
              <p className="hint" style={{ marginTop: 11 }}>Structure informs <b style={{ color: "var(--t-hi)" }}>where</b> a move would act, not <b style={{ color: "var(--t-hi)" }}>whether</b> the bias is right. Current NQ {num(nqGroup.current_price, 2)}.</p>
              <div className="sx" style={{ marginTop: 10 }}>
                <table className="grid">
                  <thead><tr><th>Level</th><th>Timeframe</th><th>Price</th><th>Status</th></tr></thead>
                  <tbody>
                    {levelRows.map((l: any) => (
                      <tr key={l.key}>
                        <td>{String(l.name ?? l.key)}</td>
                        <td>{String(l.timeframe ?? "—")}</td>
                        <td className="n">{num(l.price, 2)}</td>
                        <td><span className={`badge ${upper(l.status) === "TAPPED" ? "good" : "neutral"}`}>{upper(words(l.status))}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Acc>

            <Acc id="analogy" idx="10" title="Historical & Regime Analogues" sub="Point-in-time comparable states"
              right={<span className={`badge ${analogy.available ? "good" : "bad"}`}>{analogy.available ? `n = ${analogy.sample_size ?? "—"}` : "UNAVAILABLE"}</span>}>
              <KV k="Analogue evidence available" v={String(analogy.available ?? "—")} color={analogy.available ? "var(--bull)" : "var(--warn)"} />
              <KV k="Sample size" v={<span className="num">{analogy.sample_size ?? "—"} · effective {num(analogy.effective_sample_size, 2)}</span>} />
              <KV k="Mean similarity" v={<span className="num">{num(analogy.mean_similarity, 3)}</span>} />
              <KV k="Analogue bullish rate" v={<span className="num">{pct(analogy.bullish_probability, 2)}</span>} />
              {asList(analogy.nearest).slice(0, 3).map((n: any, i: number) => (
                <KV key={i} k={`Nearest #${i + 1}`} v={<span>{String(asObj(n).timestamp ?? "—").slice(0, 10)} · sim {num(asObj(n).similarity, 3)} · <b style={{ color: dirColor(asObj(n).actual) }}>ACTUAL {upper(words(asObj(n).actual))}</b></span>} />
              ))}
              <div className="eyebrow" style={{ marginTop: 14 }}>Current regime read</div>
              <KV k="Primary" v={upper(words(cogRegime.primary))} />
              <KV k="Secondary" v={asList(cogRegime.secondary).map(words).join(" · ") || "—"} />
              <KV k="Regime confidence" v={<span className="num">{num(cogRegime.confidence, 3)}</span>} />
              <KV k="Risk state" v={upper(words(cogRegime.risk_state))} />
              {analogy.reason && <p className="hint" style={{ marginTop: 11 }}>{String(analogy.reason)}</p>}
            </Acc>

            <Acc id="evidence" idx="11" title="Evidence Ledger & Provenance" sub="Every record with source, freshness and quality"
              right={<span className="badge info">{evidenceLedger.record_count ?? 0} RECORDS</span>}>
              <div className="sx" style={{ marginTop: 11 }}>
                <table className="grid">
                  <thead><tr><th>Evidence ID</th><th>Instrument</th><th>Source</th><th>Freshness</th><th>Quality</th></tr></thead>
                  <tbody>
                    {asList(cognitive.evidence_records).map((raw: any, i: number) => {
                      const r = asObj(raw);
                      return (
                        <tr key={i}>
                          <td className="n" style={{ fontSize: 10 }}>{String(r.evidence_id ?? "—")}</td>
                          <td>{String(r.instrument ?? "—")}</td>
                          <td style={{ fontSize: 10 }}>{String(r.source ?? "—")}</td>
                          <td><Badge value={r.freshness || "UNKNOWN"} /></td>
                          <td className="n">{num(r.quality, 2)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <KV k="Records" v={<span className="num">{evidenceLedger.record_count ?? 0} · available {evidenceLedger.available_count ?? 0} · missing {evidenceLedger.missing_count ?? 0}</span>} />
              <KV k="Ledger digest" v={<span className="hash" style={{ fontSize: 9, color: "var(--t-low)" }}>{shortHash(evidenceLedger.ledger_digest, 16, 10)}</span>} />
              <div className="eyebrow" style={{ marginTop: 14 }}>Missing evidence — never scored as neutral</div>
              {missingEvidence.map((m: any, i: number) => (
                <KV key={i} k={String(asObj(m).name ?? "—")} v={`${words(asObj(m).family)} · reliability ${num(asObj(m).reliability, 1)} · uncertainty ${num(asObj(m).uncertainty, 1)}`} color="var(--warn)" />
              ))}
              <div className="eyebrow" style={{ marginTop: 14 }}>News intelligence</div>
              <KV k="Available" v={String(news.available ?? "—")} color={news.available ? "var(--bull)" : "var(--warn)"} />
              <KV k="Article count" v={<span className="num">{news.article_count ?? "—"}</span>} />
              <KV k="Primary-source ratio" v={<span className="num">{num(news.primary_source_ratio, 2)}</span>} />
              <KV k="Policy" v={words(asObj(news.policy).status)} />
            </Acc>

            <Acc id="chart" idx="12" title="Chart Lab" sub="Upload · independent vision · three-way confluence"
              right={<span className="badge mid">EXTERNAL VISION API</span>}>
              <div className="degraded" style={{ marginTop: 12 }}>
                <span className="k">DISCLOSURE</span>
                <span className="v">The Chart Lab calls an <b>external paid vision API</b>, unlike the forecast path which runs on the local model only. Vision analyses the chart <b>before</b> seeing FIA&rsquo;s direction or yours, so the comparison stays independent.</span>
              </div>
              {phase25.latest_grade && (
                <div className="recon" style={{ marginTop: 10 }}>
                  <span className="k">LAST CONFLUENCE GRADE</span><span className="v">{String(phase25.latest_grade)}</span>
                  <span className="k">ALIGNMENT</span><span className="v num">{pct(phase25.alignment_pct, 1)}</span>
                  <span className="k">COMPLETENESS</span><span className="v num">{pct(phase25.completeness_pct, 1)}</span>
                </div>
              )}
              <div style={{ marginTop: 12 }}>
                <Link href="/chart-lab" className="cl-run" style={{ display: "inline-block", textDecoration: "none", width: "auto", padding: "10px 18px" }}>OPEN CHART LAB</Link>
              </div>
            </Acc>
          </div>
        </section>

        {/* ========================================= PAGE 03 · VALIDATION */}
        <section className={`page ${page === "validation" ? "active" : ""}`}>
          <div className="page-head">
            <div><h1 className="page-title">Validation</h1><p className="page-desc">Predictive performance and engineering health are reported separately and never merged into one score.</p></div>
          </div>

          <div className="tri">
            <div className="vcard edge">
              <div className="vk">A · Predictive edge</div>
              <div className="vv">NOT PROVEN</div>
              <p className="vd">Derived from the resolved Forward-OOS sample. The backend computes no edge-vs-chance test of its own.</p>
              <div className="vrow">
                <div><span className="k">Forward n</span><span className="v num" style={{ color: "var(--warn)" }}>{asObj(forward["4h"]).n ?? 0}</span></div>
                <div><span className="k">Needed</span><span className="v num">30</span></div>
                <div><span className="k">Target</span><span className="v num">50</span></div>
              </div>
            </div>
            <div className="vcard oos">
              <div className="vk">Forward-OOS campaign</div>
              <div className="vv">{asObj(forward["4h"]).n ?? 0} RESOLVED</div>
              <p className="vd">Append-only. Forecast is locked first; the outcome is attached only after the horizon elapses.</p>
              <div className="vrow">
                <div><span className="k">4H</span><span className="v num">{upper(words(asObj(forward["4h"]).status || "COLLECTING"))}</span></div>
                <div><span className="k">8H</span><span className="v num">{upper(words(asObj(forward["8h"]).status || "COLLECTING"))}</span></div>
              </div>
            </div>
            <div className="vcard eng">
              <div className="vk">B · Engineering health</div>
              <div className="vv">{finalCockpit.truth_ready === true ? "PASS" : "DEGRADED"}</div>
              <p className="vd"><b style={{ color: "var(--warn)" }}>Engineering PASS is not evidence of predictive skill.</b></p>
              <div className="vrow">
                <div><span className="k">Backend</span><span className="v" style={{ color: "var(--bull)" }}>{error ? "DOWN" : "LIVE"}</span></div>
                <div><span className="k">Brain</span><span className="v">{upper(words(brain.status || "UNKNOWN"))}</span></div>
                <div><span className="k">Provider</span><span className="v">{upper(words(provider.overall || "UNKNOWN"))}</span></div>
              </div>
            </div>
          </div>

          <div className="panel" style={{ marginBottom: 12 }}>
            <div className="panel-h">
              <div><h3>A · Forward-OOS Performance</h3><p className="hint" style={{ marginTop: 1 }}>Populated only when resolved observations exist.</p></div>
              <span className="badge mid">COLLECTING</span>
            </div>
            <div className="panel-b" style={{ padding: 0 }}>
              <div className="stats">
                {[
                  ["4H accuracy", asObj(forward["4h"]).accuracy, asObj(forward["4h"]).n],
                  ["8H accuracy", asObj(forward["8h"]).accuracy, asObj(forward["8h"]).n],
                ].map(([label, acc, n]: any, i: number) => (
                  <div className="stat" key={i}>
                    <div className="stat-k">{label}</div>
                    <div className={`stat-v ${finite(acc) === null ? "na" : ""}`}>{finite(acc) === null ? "INSUFFICIENT SAMPLE" : pct(acc, 2)}</div>
                    <div className="stat-n">n = {n ?? 0}</div>
                  </div>
                ))}
                <div className="stat"><div className="stat-k">Brier</div><div className="stat-v na">—</div><div className="stat-n">Requires outcomes</div></div>
                <div className="stat"><div className="stat-k">ECE / calibration</div><div className="stat-v na">—</div><div className="stat-n">Requires outcomes</div></div>
                <div className="stat"><div className="stat-k">Interval coverage</div><div className="stat-v na">NOT COMPUTED</div><div className="stat-n">No coverage metric exists</div></div>
                <div className="stat"><div className="stat-k">NO_EDGE rate</div><div className="stat-v na">NOT COMPUTED</div><div className="stat-n">Abstentions refused at lock</div></div>
                <div className="stat"><div className="stat-k">Regime-wise</div><div className="stat-v na">—</div><div className="stat-n">Requires outcomes</div></div>
                <div className="stat"><div className="stat-k">Drift monitor</div><div className="stat-v na">{upper(words(drift.status || "—"))}</div><div className="stat-n">ref {drift.reference_n ?? "—"} · recent {drift.recent_n ?? "—"}</div></div>
              </div>
              <p className="hint" style={{ padding: "12px 14px 14px" }}>Empty is the correct state for a campaign that has just been sealed. Showing a number here before observations exist is exactly the failure mode this page prevents.</p>
            </div>
          </div>

          {backtest.available && (
            <div className="panel" style={{ marginBottom: 12 }}>
              <div className="panel-h">
                <div><h3>Historical Measurement · {words(backtest.phase)}</h3><p className="hint" style={{ marginTop: 1 }}>Retrospective. Never counted as forward proof.</p></div>
                <span className="badge bad">NOT FORWARD EVIDENCE</span>
              </div>
              <div className="panel-b">
                <div className="stats" style={{ border: 0 }}>
                  <div className="stat"><div className="stat-k">4H accuracy</div><div className="stat-v" style={{ color: "var(--bear)" }}>{pct(asObj(backtest.accuracy_4h).accuracy, 2)}</div><div className="stat-n">{asObj(backtest.accuracy_4h).correct} of {asObj(backtest.accuracy_4h).resolved} resolved</div></div>
                  <div className="stat"><div className="stat-k">8H accuracy</div><div className="stat-v" style={{ color: "var(--bear)" }}>{pct(asObj(backtest.accuracy_8h).accuracy, 2)}</div><div className="stat-n">{asObj(backtest.accuracy_8h).correct} of {asObj(backtest.accuracy_8h).resolved} resolved</div></div>
                  <div className="stat"><div className="stat-k">4H Brier</div><div className="stat-v" style={{ color: "var(--bear)" }}>{num(asObj(backtest.brier_4h).brier, 4)}</div><div className="stat-n">n {asObj(backtest.brier_4h).n} · worse than 0.25</div></div>
                  <div className="stat"><div className="stat-k">8H Brier</div><div className="stat-v" style={{ color: "var(--bear)" }}>{num(asObj(backtest.brier_8h).brier, 4)}</div><div className="stat-n">n {asObj(backtest.brier_8h).n} · worse than 0.25</div></div>
                  <div className="stat"><div className="stat-k">Total forecasts</div><div className="stat-v">{backtest.forecasts ?? "—"}</div><div className="stat-n">{asObj(backtest.predictions).BULLISH ?? "—"} bullish · {asObj(backtest.predictions).BEARISH ?? "—"} bearish</div></div>
                </div>
                {perf.note && (
                  <div className="tilt" style={{ marginTop: 12 }}>
                    <span className="k">DISCLOSURE</span>
                    <span className="v"><b>{upper(words(perf.status))}.</b> {String(perf.note)}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="cockpit" style={{ marginBottom: 12 }}>
            {(["confidence_4h", "confidence_8h"] as const).map((key) => (
              <div className="panel" key={key}>
                <div className="panel-h">
                  <div><h3>Confidence Buckets · {key.endsWith("4h") ? "4H" : "8H"}</h3><p className="hint" style={{ marginTop: 1 }}>Is stated confidence informative?</p></div>
                  <span className="badge neutral">HISTORICAL</span>
                </div>
                <div className="panel-b">
                  {asList(backtest[key]).map((raw: any, i: number) => {
                    const b = asObj(raw);
                    const acc = finite(b.accuracy) ?? 0;
                    return (
                      <div className="bkt" key={i}>
                        <span className="bkt-k">{String(b.band ?? "—")}</span>
                        <div className="bkt-t"><i style={{ width: `${Math.max(0, Math.min(100, acc))}%`, background: acc >= 50 ? "var(--bull)" : "var(--bear)" }} /><span className="ref" style={{ left: "50%" }} /></div>
                        <span className="bkt-v num" style={{ color: acc >= 50 ? "var(--bull)" : "var(--bear)" }}>{pct(b.accuracy, 2)}</span>
                      </div>
                    );
                  })}
                  <p className="hint" style={{ marginTop: 11 }}>The marker is chance. Bands below it mean stated confidence was not informative at that level.</p>
                </div>
              </div>
            ))}
          </div>

          <div className="panel-h" style={{ border: 0, padding: "0 0 9px" }}>
            <div><h3 style={{ fontSize: 12 }}>B · System Health</h3><p className="hint" style={{ marginTop: 1 }}>Component state at last snapshot.</p></div>
          </div>
          <div className="health" style={{ marginBottom: 12 }}>
            <div className="hi"><span className={`dot ${error ? "bad" : "ok"}`} /><div className="hi-b"><div className="hi-k">Backend</div><div className="hi-v">{error ? "UNAVAILABLE" : "LIVE"}</div></div></div>
            <div className="hi"><span className={`dot ${tone(brain.status) === "good" ? "ok" : "warn"}`} /><div className="hi-b"><div className="hi-k">GPT-OSS Brain</div><div className="hi-v">{upper(words(brain.status || "UNKNOWN"))} · {String(brain.model ?? "—")}</div></div></div>
            {Object.entries(sourceHealth).map(([k, raw]) => {
              const s = asObj(raw);
              const t = tone(s.status);
              return (
                <div className="hi" key={k}>
                  <span className={`dot ${t === "good" ? "ok" : t === "bad" ? "bad" : "warn"}`} />
                  <div className="hi-b"><div className="hi-k">{k.replace(/_/g, " ")}</div>
                    <div className="hi-v">{upper(words(s.status))}{finite(s.age_seconds) !== null && (finite(s.age_seconds) ?? 0) > 3600 ? ` · ${((finite(s.age_seconds) ?? 0) / 3600).toFixed(1)}h` : ""}</div></div>
                </div>
              );
            })}
          </div>

          <div className="acc">
            <Acc id="model" idx="—" title="Model Identity & Runtime" sub="Exact GPT-OSS identity and status" right={<span className="badge neutral">COLLAPSED</span>}>
              <KV k="Model" v={<span className="num">{String(brain.model ?? "—")}</span>} />
              <KV k="Brain status" v={upper(words(brain.status || "—"))} />
              <KV k="Ollama" v={upper(words(asObj(brain.ollama).status || "—"))} />
              <KV k="Cognitive architecture" v={<span className="num">{String(cognitive.architecture_version ?? "—")}</span>} />
              <KV k="Forecast ID" v={<span className="num" style={{ fontSize: 10 }}>{String(cognitive.forecast_id ?? "—")}</span>} />
              <KV k="Paid API at prediction time" v="FALSE" color="var(--bull)" />
            </Acc>

            <Acc id="integrity" idx="—" title="Evidence Integrity & Ledger" sub="Hashes and append-only state" right={<span className="badge neutral">COLLAPSED</span>}>
              <KV k="Pre-move forecast ID" v={<span className="num" style={{ fontSize: 10 }}>{String(premove.forecast_id ?? "—")}</span>} />
              <KV k="Evidence hash" v={<span className="hash" style={{ fontSize: 9, color: "var(--t-low)" }}>{String(premove.evidence_hash ?? "—")}</span>} />
              <KV k="Ledger seq" v={<span className="num">{asObj(premove.ledger).seq ?? "—"}</span>} />
              <KV k="Row hash" v={<span className="hash" style={{ fontSize: 9, color: "var(--t-low)" }}>{shortHash(asObj(premove.ledger).row_hash, 16, 10)}</span>} />
              <KV k="Prev hash" v={<span className="hash" style={{ fontSize: 9, color: "var(--t-low)" }}>{shortHash(asObj(premove.ledger).prev_hash, 16, 10)}</span>} />
              <KV k="Critical missing" v={asList(dataTruth.critical_missing).join(" · ") || "none"} />
              <KV k="Stale sources" v={asList(dataTruth.stale_sources).join(" · ") || "none"} />
              <p className="hint" style={{ marginTop: 10 }}>The ledger is tamper-<b style={{ color: "var(--t-hi)" }}>evident</b> but not tamper-<b style={{ color: "var(--t-hi)" }}>proof</b> against whoever owns the filesystem. That limitation is surfaced rather than implied away.</p>
            </Acc>

            <Acc id="calib" idx="—" title="Calibration Model & Dataset Split" sub="Where the published probability is shaped" right={<span className="badge mid">BASE-RATE TILT</span>}>
              <KV k="Method" v={String(asObj(calibration.model).method ?? "—")} />
              <KV k="Fit sample · 8H" v={<span className="num">n = {asObj(calibration.model).n ?? "—"}</span>} />
              <KV k="Raw probability" v={<span className="num">{num(calibration.raw_probability, 3)}</span>} />
              <KV k="Calibrated probability" v={<span className="num">{num(calibration.calibrated_probability, 3)}</span>} />
              <KV k="Development window" v={<span className="num" style={{ fontSize: 10 }}>{String(asObj(calibration.dataset_split).development ?? "—")}</span>} />
              <KV k="Holdout window" v={<span className="num" style={{ fontSize: 10 }}>{String(asObj(calibration.dataset_split).holdout ?? "—")}</span>} />
              <KV k="Holdout used for fitting" v={String(asObj(calibration.dataset_split).holdout_used_for_fitting ?? "—")} color="var(--bull)" />
              <KV k="No-information tilt · 8H" v={<span className="num">{signed(h8cal.no_information_tilt_points, 2)} pts</span>} color="var(--warn)" />
              <KV k="No-information tilt · 4H" v={<span className="num">{signed(h4cal.no_information_tilt_points, 2)} pts</span>} color="var(--warn)" />
              <KV k="Calibration may decide direction" v={h8.calibration_flips_direction === false ? "NO" : "—"} color="var(--bull)" />
              {h8cal.tilt_note && <p className="hint" style={{ marginTop: 10 }}>{String(h8cal.tilt_note)}</p>}
            </Acc>

            <Acc id="candidates" idx="—" title="Rejected Candidate Engines" sub="Candidates tested and not adopted" right={<span className="badge bad">NOT ADOPTED</span>}>
              <p className="hint" style={{ marginTop: 11 }}>Candidate engines are evaluated against BASE_FIA on an untouched holdout and adopted only if they win. Both current candidates were rejected on evidence.</p>
              <div className="eyebrow" style={{ marginTop: 14 }}>Phase 33 · Institutional Pre-Move</div>
              <KV k="Untouched holdout rows" v={<span className="num">78</span>} />
              <KV k="4H accuracy" v={<span className="num">37.33% vs BASE_FIA 53.33%</span>} color="var(--bear)" />
              <KV k="8H accuracy" v={<span className="num">38.71% vs BASE_FIA 48.39%</span>} color="var(--bear)" />
              <KV k="Approved for live probability" v="FALSE" color="var(--bear)" />
              <KV k="Verdict" v="NOT ADOPTED — underperformed the baseline" color="var(--bear)" />
              <div className="eyebrow" style={{ marginTop: 14 }}>Phase 34 · All-Points Pre-Move</div>
              <KV k="Data sources available" v={<span className="num">1 of 13</span>} color="var(--warn)" />
              <KV k="Historical enriched rows" v={<span className="num">0</span>} color="var(--warn)" />
              <KV k="Replay status" v="BLOCKED_BY_MISSING_HISTORICAL_INSTITUTIONAL_INPUTS" color="var(--warn)" />
              <KV k="Verdict" v="NEVER VALIDATED — code coverage without evidence coverage" color="var(--warn)" />
              <p className="hint" style={{ marginTop: 11 }}>Neither candidate touches the live 4H/8H forecast, Three-Brain, Forward-OOS or any dashboard value — verified by zero imports in the live path. Both are excluded from trader navigation.</p>
            </Acc>

            <Acc id="policy" idx="—" title="Policy Invariants" sub="What the system refuses to do" right={<span className="badge neutral">COLLAPSED</span>}>
              <div className="health" style={{ marginTop: 11 }}>
                {Object.entries(asObj(cognitive.policy)).concat(Object.entries(asObj(premove.policy))).map(([k, v], i) => (
                  <div className="hi" key={`${k}-${i}`}>
                    <span className={`dot ${v === true || v === false ? "ok" : "warn"}`} />
                    <div className="hi-b"><div className="hi-k">{k.replace(/_/g, " ")}</div><div className="hi-v">{String(v).toUpperCase()}</div></div>
                  </div>
                ))}
              </div>
            </Acc>
          </div>

          <div className="footnote">
            <span className="k">Reminder</span>
            <span className="hint">Engineering PASS is not evidence of predictive skill. Predictive edge remains NOT PROVEN until genuinely new, unseen Forward-OOS observations resolve.</span>
          </div>
        </section>
      </div>
    </div>
  );
}
