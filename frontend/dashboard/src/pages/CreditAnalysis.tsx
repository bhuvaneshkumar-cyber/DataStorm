/**
 * Credit analysis: upload a statement, get a scored and explained credit view.
 *
 * This is the UI for the ml_service ingestion + scoring pipeline:
 *   statement -> derived features -> hybrid score + risk assessment
 *             -> transaction ledger -> per-metric breakdown + coaching
 *
 * Everything shown here comes from the live service. Where the statement could
 * not evidence something, the page says so rather than filling the gap
 * silently — the provenance is the point.
 */

import { useEffect, useRef, useState } from 'react';
import {
  CircleAlert,
  FileUp,
  Gauge,
  Info,
  Lightbulb,
  Loader,
  RotateCcw,
  ShieldCheck,
  TrendingUp,
  Upload,
} from 'lucide-react';
import {
  analyzeStatement,
  fetchServiceHealth,
  type MetricDetail,
  type ServiceHealth,
  type StatementScoreResponse,
} from '@/lib/api';

const CATEGORY_LABELS: Record<string, string> = {
  income_quality: 'Income quality',
  spending_behavior: 'Spending behaviour',
  liquidity: 'Liquidity',
  gig_stability: 'Gig stability',
};

const FEATURE_LABELS: Record<string, string> = {
  age: 'Age',
  primary_gig_platform: 'Primary platform',
  platform_customer_rating: 'Platform rating',
  completed_gigs_per_week: 'Gigs per week',
  average_weekly_payout: 'Average weekly payout',
  payout_volatility_index: 'Payout volatility',
  active_platform_hours_per_week: 'Active hours per week',
  resilience_stash_balance: 'Resilience stash',
};

const MONEY_FEATURES = new Set(['average_weekly_payout', 'resilience_stash_balance']);

function formatINR(amount: number) {
  return `₹${Math.round(amount).toLocaleString('en-IN')}`;
}

function formatFeature(key: string, value: number | string) {
  if (typeof value === 'string') return value;
  if (MONEY_FEATURES.has(key)) return formatINR(value);
  return String(value);
}

/**
 * Score bands drive tone, so a colour never contradicts the decision text.
 *
 * Named strong/fair/weak rather than reusing the dashboard's `status-*` classes:
 * there, `status-high` is green because it labels "high savings consistency".
 * Reusing it here would paint a failing metric green.
 */
function toneForScore(score: number, max: number): 'strong' | 'fair' | 'weak' {
  const pct = (score / max) * 100;
  if (pct >= 75) return 'strong';
  if (pct >= 50) return 'fair';
  return 'weak';
}

/* ------------------------------------------------------------------ */
/*  Pieces                                                            */
/* ------------------------------------------------------------------ */

function MetricRow({ metric }: { metric: MetricDetail }) {
  return (
    <div className="metric-row" data-testid={`row-metric-${metric.name}`}>
      <div className="metric-head">
        <span className="metric-name" title={metric.description}>
          {metric.name.replace(/_/g, ' ')}
        </span>
        <span className={`metric-status tone-${toneForScore(metric.score, 100)}`}>
          {metric.status}
        </span>
      </div>
      <div className="metric-track" aria-label={`${metric.name} scores ${metric.score} out of 100`}>
        <div className={`metric-fill tone-${toneForScore(metric.score, 100)}`} style={{ width: `${metric.score}%` }} />
      </div>
      <div className="metric-foot">
        <span>{metric.description}</span>
        <strong>{metric.score}/100</strong>
      </div>
    </div>
  );
}

function UploadPanel({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (file: File, overrides: Record<string, string>) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [age, setAge] = useState('');
  const [rating, setRating] = useState('');
  const [hours, setHours] = useState('');

  return (
    <form
      className="card upload-card"
      data-testid="form-statement-upload"
      onSubmit={(event) => {
        event.preventDefault();
        if (file) onSubmit(file, { age, platform_customer_rating: rating, active_platform_hours_per_week: hours });
      }}
    >
      <div className="card-head" style={{ padding: 0 }}>
        <div>
          <h2 className="card-title">Analyse a statement</h2>
          <p className="card-kicker">
            PDF, CSV, Excel, Word or text. Your file is parsed in memory and deleted
            right after scoring.
          </p>
        </div>
        <FileUp size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
      </div>

      <button
        type="button"
        className={`dropzone${file ? ' has-file' : ''}`}
        onClick={() => inputRef.current?.click()}
        data-testid="button-choose-file"
      >
        <Upload size={20} strokeWidth={1.7} aria-hidden="true" />
        <strong>{file ? file.name : 'Choose your bank or payout statement'}</strong>
        <span>{file ? `${(file.size / 1024).toFixed(0)} KB — click to replace` : 'Up to 25 MB'}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.csv,.xlsx,.xls,.xlsm,.docx,.doc,.txt"
        hidden
        data-testid="input-statement-file"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />

      <p className="upload-note">
        <Info size={13} /> A statement cannot show your age, platform rating or hours
        worked. Add them for a sharper score, or leave blank to use conservative defaults.
      </p>

      <div className="upload-fields">
        <label>
          Age
          <input type="number" min={18} max={75} value={age} placeholder="30"
            data-testid="input-age" onChange={(e) => setAge(e.target.value)} />
        </label>
        <label>
          Platform rating
          <input type="number" min={1} max={5} step={0.1} value={rating} placeholder="4.0"
            data-testid="input-rating" onChange={(e) => setRating(e.target.value)} />
        </label>
        <label>
          Hours / week
          <input type="number" min={0} max={120} value={hours} placeholder="40"
            data-testid="input-hours" onChange={(e) => setHours(e.target.value)} />
        </label>
      </div>

      <button className="primary-button" type="submit" disabled={!file || busy} data-testid="button-analyse">
        {busy ? <Loader size={14} className="spin" /> : <Gauge size={14} />}
        {busy ? 'Reading your statement…' : 'Analyse statement'}
      </button>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export default function CreditAnalysis({ announce }: { announce: (message: string) => void }) {
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [result, setResult] = useState<StatementScoreResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchServiceHealth()
      .then((data) => !cancelled && setHealth(data))
      .catch((err: Error) => !cancelled && setHealthError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (file: File, overrides: Record<string, string>) => {
    setBusy(true);
    setError(null);
    try {
      const data = await analyzeStatement(file, {
        age: overrides.age ? Number(overrides.age) : undefined,
        platform_customer_rating: overrides.platform_customer_rating
          ? Number(overrides.platform_customer_rating)
          : undefined,
        active_platform_hours_per_week: overrides.active_platform_hours_per_week
          ? Number(overrides.active_platform_hours_per_week)
          : undefined,
      });
      setResult(data);
      announce(`Statement analysed — score ${Math.round(data.score.final_score)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong reading that file.');
    } finally {
      setBusy(false);
    }
  };

  const score = result?.score;
  const risk = score?.risk_assessment ?? null;
  const metrics = result?.metric_analysis ?? null;
  const analysis = result?.statement_analysis ?? null;

  return (
    <>
      <div className="page-title">
        <div className="eyebrow">
          <span className="eyebrow-dot" /> Credit analysis
        </div>
        <h1>Turn your earnings into credit.</h1>
        <p>
          Upload a statement and we read the story your income already tells — no
          salary slip, no credit history required.
        </p>
      </div>

      {healthError && (
        <div className="notice notice-warn" role="status" data-testid="notice-health">
          <CircleAlert size={15} />
          <span>The scoring service is unreachable: {healthError}</span>
        </div>
      )}
      {health && !health.ingestion_formats.pdf && (
        <div className="notice notice-warn" role="status">
          <CircleAlert size={15} />
          <span>PDF parsing is not installed on this deployment — use a CSV or Excel export.</span>
        </div>
      )}
      {health && health.mode === 'rules_only' && (
        <div className="notice notice-warn" role="status">
          <CircleAlert size={15} />
          <span>The ML model is unavailable, so scores are rule-based only and indicative.</span>
        </div>
      )}

      <div className="analysis-grid">
        <UploadPanel busy={busy} onSubmit={submit} />

        {error && (
          <div className="error-state" role="alert" data-testid="state-analysis-error">
            <CircleAlert size={27} strokeWidth={1.7} />
            <h2>We couldn't read that statement</h2>
            <p>{error}</p>
            <button className="primary-button" type="button" onClick={() => setError(null)}>
              <RotateCcw size={14} /> Try another file
            </button>
          </div>
        )}

        {score && (
          <article className="card score-summary" data-testid="card-score-summary">
            <div className="card-head" style={{ padding: 0 }}>
              <div>
                <h2 className="card-title">Your credit view</h2>
                <p className="card-kicker">
                  {score.ml_available ? 'Rules + model' : 'Rules only'} · scored in{' '}
                  {score.latency_ms.toFixed(0)} ms
                </p>
              </div>
              <ShieldCheck size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
            </div>

            <div className="score-row">
              <div>
                <div className="money-label">Score</div>
                <div className="score-number" data-testid="text-final-score">
                  {Math.round(score.final_score)}
                  <span className="score-outof">/800</span>
                </div>
                <div className={`metric-status tone-${toneForScore(score.final_score, 800)}`}>
                  {score.category}
                </div>
              </div>
              {risk && (
                <dl className="risk-facts" data-testid="list-risk-facts">
                  <div>
                    <dt>Decision</dt>
                    <dd data-testid="text-decision">{risk.decision}</dd>
                  </div>
                  <div>
                    <dt>Grade</dt>
                    <dd>
                      {risk.risk_grade.code} · {risk.risk_grade.label}
                    </dd>
                  </div>
                  <div>
                    <dt>Indicative rate</dt>
                    <dd>{risk.indicative_interest_rate_pct}%</dd>
                  </div>
                  <div>
                    <dt>Credit limit</dt>
                    <dd>{formatINR(risk.max_credit_limit_inr)}</dd>
                  </div>
                  <div>
                    <dt>Tenor</dt>
                    <dd>{risk.recommended_tenor_months} months</dd>
                  </div>
                </dl>
              )}
            </div>

            {risk && risk.early_warning_signals.length > 0 && (
              <div className="warning-list" data-testid="list-warnings">
                <h3 className="card-title">Watch-outs</h3>
                {risk.early_warning_signals.map((signal) => (
                  <div className="warning-item" key={signal.code}>
                    <CircleAlert size={14} />
                    <div>
                      <strong>{signal.title}</strong>
                      <span>{signal.detail}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {risk && risk.conditions.length > 0 && (
              <ul className="modal-list" data-testid="list-conditions">
                {risk.conditions.map((condition) => (
                  <li key={condition}>
                    <ShieldCheck size={14} />
                    {condition}
                  </li>
                ))}
              </ul>
            )}
          </article>
        )}

        {metrics && (
          <article className="card metrics-card" data-testid="card-metrics">
            <div className="card-head" style={{ padding: 0 }}>
              <div>
                <h2 className="card-title">What's driving it</h2>
                <p className="card-kicker">
                  {metrics.coverage.transactions} transactions across{' '}
                  {metrics.coverage.months_observed} month
                  {metrics.coverage.months_observed === 1 ? '' : 's'} (
                  {metrics.coverage.period_start} → {metrics.coverage.period_end})
                </p>
              </div>
              <TrendingUp size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
            </div>

            <div className="category-grid" data-testid="grid-categories">
              {Object.entries(metrics.category_scores).map(([key, value]) => (
                <div className="category-tile" key={key}>
                  <span className="category-label">{CATEGORY_LABELS[key] ?? key}</span>
                  <strong className={`category-score tone-${toneForScore(value, 100)}`}>
                    {Math.round(value)}
                  </strong>
                  <span className="category-weight">{metrics.category_weights[key]}% weight</span>
                </div>
              ))}
            </div>

            <div className="metric-list">
              {Object.values(metrics.metrics)
                .sort((a, b) => a.score - b.score)
                .map((metric) => (
                  <MetricRow key={metric.name} metric={metric} />
                ))}
            </div>
          </article>
        )}

        {metrics && (metrics.recommended_actions.length > 0 || metrics.strengths.length > 0) && (
          <article className="card coaching-card" data-testid="card-coaching">
            <div className="card-head" style={{ padding: 0 }}>
              <div>
                <h2 className="card-title">What would lift your score</h2>
                <p className="card-kicker">Ordered by how much each would move the number</p>
              </div>
              <Lightbulb size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
            </div>
            {metrics.strengths.length > 0 && (
              <div className="chip-row" data-testid="list-strengths">
                {metrics.strengths.map((strength) => (
                  <span className="chip chip-good" key={strength}>
                    {strength}
                  </span>
                ))}
              </div>
            )}
            {metrics.weaknesses.length > 0 && (
              <div className="chip-row" data-testid="list-weaknesses">
                {metrics.weaknesses.map((weakness) => (
                  <span className="chip chip-warn" key={weakness}>
                    {weakness}
                  </span>
                ))}
              </div>
            )}
            <ol className="action-list" data-testid="list-actions">
              {metrics.recommended_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ol>
          </article>
        )}

        {analysis && (
          <article className="card provenance-card" data-testid="card-provenance">
            <div className="card-head" style={{ padding: 0 }}>
              <div>
                <h2 className="card-title">Where these numbers came from</h2>
                <p className="card-kicker">
                  Read as {analysis.source_format.toUpperCase()}
                  {analysis.extraction_method ? ` via ${analysis.extraction_method}` : ''}
                </p>
              </div>
              <Info size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
            </div>

            <div className="provenance-lists">
              <div>
                <h3>From your statement</h3>
                <ul>
                  {Object.entries(analysis.derived_features).map(([key, value]) => (
                    <li key={key}>
                      <span>{FEATURE_LABELS[key] ?? key}</span>
                      <strong>{formatFeature(key, value)}</strong>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>Supplied or assumed</h3>
                <ul>
                  {Object.entries(analysis.supplied_features).map(([key, entry]) => (
                    <li key={key}>
                      <span>{FEATURE_LABELS[key] ?? key}</span>
                      <strong>
                        {formatFeature(key, entry.value)}
                        <em className={entry.source === 'caller' ? 'src-caller' : 'src-default'}>
                          {entry.source === 'caller' ? 'you' : 'default'}
                        </em>
                      </strong>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {analysis.warnings.length > 0 && (
              <div className="warning-list">
                {analysis.warnings.map((warning) => (
                  <div className="warning-item" key={warning}>
                    <CircleAlert size={14} />
                    <div>
                      <span>{warning}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </article>
        )}
      </div>
    </>
  );
}
