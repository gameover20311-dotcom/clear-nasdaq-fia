'use client';

import { useEffect, useMemo, useState } from 'react';

type Signal = {
  name: string;
  score: number;
  weight: number;
  detail: string;
  freshness: string;
};

type Forecast = {
  direction: string;
  bullish_probability: number;
  bearish_probability: number;
  confidence: number;
  regime: string;
  status: string;
  score: number;
  data_coverage: number;
  generated_at?: string;
  symbol?: string;
  horizon_hours?: number;
  source_status?: Record<string, string>;
  signals: Signal[];
  invalidation: string[];
};

const API_URL = 'http://localhost:8000/api/forecast';

function pct(value: number) {
  return `${Number(value ?? 0).toFixed(1)}%`;
}

function scoreLabel(value: number) {
  if (value > 0.15) return 'BULLISH';
  if (value < -0.15) return 'BEARISH';
  return 'NEUTRAL';
}

function freshnessLabel(value: string) {
  if (!value || value === 'missing') return 'WAIT';
  return value.toUpperCase();
}

function formatTime(value?: string) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function signalTone(score: number) {
  if (score > 0.05) return 'positive';
  if (score < -0.05) return 'negative';
  return 'neutral';
}

export default function Page() {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const response = await fetch(API_URL, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (!active) return;
        setForecast(data);
        setUpdated(new Date());
        setError('');
      } catch {
        if (active) setError('Backend unavailable — make sure the FIA API is running on port 8000.');
      }
    };

    load();
    const id = window.setInterval(load, 30000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const signals = forecast?.signals ?? [];

  const positives = useMemo(
    () => signals.filter((s) => Number(s.score) > 0.05).sort((a, b) => b.score - a.score).slice(0, 3),
    [signals]
  );

  const negatives = useMemo(
    () => signals.filter((s) => Number(s.score) < -0.05).sort((a, b) => a.score - b.score).slice(0, 3),
    [signals]
  );

  const status = forecast?.status ?? 'CONNECTING';
  const direction = forecast?.direction ?? 'NEUTRAL';
  const bullish = forecast?.bullish_probability ?? 0;
  const bearish = forecast?.bearish_probability ?? 0;
  const confidence = forecast?.confidence ?? 0;
  const coverage = (forecast?.data_coverage ?? 0) * 100;
  const score = forecast?.score ?? 0;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">F</div>
          <div>
            <strong>CLEAR NASDAQ</strong>
            <span>FIA INTELLIGENCE</span>
          </div>
        </div>

        <nav>
          <a className="nav-item active" href="#overview"><span>◈</span> Overview</a>
          <a className="nav-item" href="#signals"><span>◌</span> Signal Engine</a>
          <a className="nav-item" href="#sources"><span>◫</span> Data Sources</a>
          <a className="nav-item" href="#invalidation"><span>△</span> Invalidation</a>
          <a className="nav-item" href="#performance"><span>↗</span> Performance</a>
        </nav>

        <div className="sidebar-footer">
          <div className="system-dot" />
          <div>
            <small>SYSTEM</small>
            <strong>LIVE MONITORING</strong>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <div className="eyebrow">MARKET INTELLIGENCE TERMINAL</div>
            <h1>NASDAQ-100 / NQ</h1>
          </div>
          <div className="topbar-right">
            <span className="live-pill"><i /> LIVE</span>
            <span className="update-text">Updated {updated ? updated.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '—'}</span>
            <button className="refresh" onClick={() => window.location.reload()}>Refresh</button>
          </div>
        </header>

        {error && (
          <div className="alert">
            <strong>CONNECTION</strong>
            <span>{error}</span>
          </div>
        )}

        <div className="dashboard" id="overview">
          <section className="hero-card">
            <div className="hero-copy">
              <div className="status-row">
                <span className={`status-badge ${status.toLowerCase()}`}>{status}</span>
                <span className="direction-badge">{direction}</span>
                <span className="horizon">NEXT {forecast?.horizon_hours ?? 4}–{(forecast?.horizon_hours ?? 4) + 4} HOURS</span>
              </div>

              <div className="hero-title">
                <span>FIA FORECAST</span>
                <h2>{pct(bullish)} <small>BULLISH</small></h2>
                <p>Probability-weighted directional outlook for the next forecast window.</p>
              </div>

              <div className="probability-bar">
                <div className="bull-fill" style={{ width: `${Math.max(0, Math.min(100, bullish))}%` }} />
              </div>
              <div className="probability-labels">
                <span><b>{pct(bullish)}</b> Bullish</span>
                <span><b>{pct(bearish)}</b> Bearish</span>
              </div>
            </div>

            <div className="gauge-wrap">
              <div className="gauge" style={{ ['--p' as string]: `${bullish}%` }}>
                <div className="gauge-inner">
                  <strong>{pct(confidence)}</strong>
                  <span>CONFIDENCE</span>
                </div>
              </div>
              <div className="gauge-note">
                <span>MODEL SCORE</span>
                <b className={score >= 0 ? 'positive-text' : 'negative-text'}>{score.toFixed(3)}</b>
              </div>
            </div>
          </section>

          <section className="metric-grid">
            <Metric title="Market Regime" value={forecast?.regime ?? '—'} hint="Current regime classification" />
            <Metric title="Data Coverage" value={`${coverage.toFixed(0)}%`} hint="Live signal availability" />
            <Metric title="Model Status" value={status} hint="Engine health state" />
            <Metric title="Last Forecast" value={formatTime(forecast?.generated_at)} hint="UTC generation timestamp" />
          </section>

          <section className="content-grid">
            <div className="panel signals-panel" id="signals">
              <PanelHeader title="FIA Signal Engine" subtitle="Weighted factors driving the forecast" />
              <div className="signal-list">
                {signals.length === 0 && <div className="empty">Waiting for forecast signals…</div>}
                {signals.map((signal) => {
                  const tone = signalTone(Number(signal.score));
                  const width = Math.min(100, Math.abs(Number(signal.score)) * 100);
                  return (
                    <div className="signal" key={signal.name}>
                      <div className="signal-main">
                        <div className={`signal-icon ${tone}`}>{tone === 'positive' ? '↑' : tone === 'negative' ? '↓' : '•'}</div>
                        <div className="signal-copy">
                          <div className="signal-name">{signal.name}</div>
                          <div className="signal-detail">{signal.detail}</div>
                        </div>
                      </div>
                      <div className="signal-mid">
                        <div className="score-track">
                          <div className={`score-fill ${tone}`} style={{ width: `${width}%` }} />
                        </div>
                        <span>W {Number(signal.weight ?? 0).toFixed(2)}</span>
                      </div>
                      <div className="signal-value">
                        <strong>{signal.freshness === 'missing' ? 'WAIT' : Number(signal.score).toFixed(2)}</strong>
                        <small>{freshnessLabel(signal.freshness)}</small>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="panel why-panel">
              <PanelHeader title="Why This Forecast?" subtitle="Highest-impact active factors" />
              <div className="impact-block">
                <div className="impact-heading positive-text">SUPPORTING BULLISH BIAS</div>
                {positives.length ? positives.map((s) => (
                  <Impact key={s.name} signal={s} />
                )) : <div className="empty">No strong bullish factors detected.</div>}
              </div>
              <div className="divider" />
              <div className="impact-block">
                <div className="impact-heading negative-text">PRESSURING THE MODEL</div>
                {negatives.length ? negatives.map((s) => (
                  <Impact key={s.name} signal={s} />
                )) : <div className="empty">No strong bearish factors detected.</div>}
              </div>
            </div>
          </section>

          <section className="content-grid lower-grid">
            <div className="panel" id="sources">
              <PanelHeader title="Data Source Health" subtitle="Provider availability behind the current forecast" />
              <div className="source-list">
                {Object.entries(forecast?.source_status ?? {
                  market: 'waiting',
                  news: 'waiting',
                  macro: 'waiting',
                  earnings: 'waiting',
                }).map(([key, value]) => (
                  <div className="source-row" key={key}>
                    <span className="source-name">{key.replace('_', ' ')}</span>
                    <span className={`source-status ${String(value).toLowerCase().includes('missing') || String(value).toLowerCase() === 'waiting' ? 'waiting' : 'online'}`}>
                      <i /> {value}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel" id="invalidation">
              <PanelHeader title="Invalidation Conditions" subtitle="What would weaken or invalidate the current view" />
              <div className="invalidation-list">
                {(forecast?.invalidation ?? []).length ? (
                  forecast!.invalidation.map((item) => (
                    <div className="invalidation-item" key={item}>
                      <span>!</span>
                      <p>{item}</p>
                    </div>
                  ))
                ) : (
                  <div className="empty">No invalidation conditions returned by the engine.</div>
                )}
              </div>
            </div>
          </section>

          <section className="panel performance-placeholder" id="performance">
            <PanelHeader title="Performance Engine" subtitle="Reserved for historical backtesting and live forecast evaluation" />
            <div className="coming-grid">
              <div><span>WIN RATE</span><b>—</b></div>
              <div><span>FORECASTS</span><b>—</b></div>
              <div><span>AVG RETURN</span><b>—</b></div>
              <div><span>CALIBRATION</span><b>—</b></div>
            </div>
            <p className="placeholder-note">No performance figures are fabricated here. Once the Backtesting + Performance Engine is connected, this section can consume its real metrics.</p>
          </section>

          <footer className="footer">
            <span>CLEAR NASDAQ FIA</span>
            <span>Live refresh: 30s</span>
            <span>Backend: localhost:8000</span>
          </footer>
        </div>
      </section>
    </main>
  );
}

function Metric({ title, value, hint }: { title: string; value: string; hint: string }) {
  return (
    <div className="metric-card">
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </div>
  );
}

function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="panel-header">
      <div>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
        <span className="panel-mark">FIA</span>
    </div>
  );
}

function Impact({ signal }: { signal: Signal }) {
  const score = Number(signal.score);
  return (
    <div className="impact-row">
      <div>
        <strong>{signal.name}</strong>
        <small>{signal.detail}</small>
      </div>
      <b className={score >= 0 ? 'positive-text' : 'negative-text'}>{score >= 0 ? '+' : ''}{score.toFixed(2)}</b>
    </div>
  );
}
