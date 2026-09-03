/**
 * The alternative credit page: score, why it is what it is, and a statement
 * upload for anyone who wants to be scored on evidence they already hold.
 *
 * Three sources of the same number sit side by side -- the profile-derived
 * score, the ledger metric breakdown, and an uploaded statement -- because they
 * answer different questions: how creditworthy, why, and on what evidence.
 */

import { useRef, useState } from 'react';
import { FileUp, Gauge, Info, Upload } from 'lucide-react';
import { credit, health } from '@/lib/api';
import { useAction, useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatINR, formatNumber, humanise } from '@/lib/format';
import { CategoryScoreBars, MetricBars, ScoreMeter } from '@/components/charts';
import {
  AsyncSection,
  Badge,
  Card,
  ErrorBanner,
  InlineSpinner,
  PageHeader,
} from '@/components/primitives';
import type { CreditScore, StatementScore } from '@/lib/types';

const MONEY_FEATURES = new Set(['average_weekly_payout', 'resilience_stash_balance']);

function formatFeature(key: string, value: number | string) {
  if (typeof value === 'string') return value;
  return MONEY_FEATURES.has(key) ? formatINR(value) : String(value);
}

const DECISION_TONE = {
  APPROVE: 'positive',
  REFER: 'warning',
  DECLINE: 'negative',
} as const;

/** The underwriting view, shared by the profile score and any uploaded statement. */
function RiskPanel({ score }: { score: CreditScore }) {
  const { t } = useI18n();
  const assessment = score.risk_assessment;
  if (!assessment) return null;

  return (
    <>
      <dl className="field-list two-column">
        <div className="field-row">
          <dt>{t('credit.grade')}</dt>
          <dd>
            {assessment.risk_grade.code} · {assessment.risk_grade.label}
          </dd>
        </div>
        <div className="field-row">
          <dt>{t('credit.decision')}</dt>
          <dd>
            <Badge tone={DECISION_TONE[assessment.decision]}>{assessment.decision}</Badge>
          </dd>
        </div>
        <div className="field-row">
          <dt>{t('credit.rate')}</dt>
          <dd>{assessment.indicative_interest_rate_pct}% p.a.</dd>
        </div>
        <div className="field-row">
          <dt>{t('credit.limit')}</dt>
          <dd>{formatINR(assessment.max_credit_limit_inr)}</dd>
        </div>
        <div className="field-row">
          <dt>{t('credit.tenor')}</dt>
          <dd>{assessment.recommended_tenor_months} months</dd>
        </div>
        <div className="field-row">
          <dt>{t('credit.rules')} / {t('credit.model')}</dt>
          <dd>
            {formatNumber(score.rule_score, 0)} /{' '}
            {score.ml_score === null ? '—' : formatNumber(score.ml_score, 0)}
          </dd>
        </div>
      </dl>

      {assessment.early_warning_signals.length > 0 && (
        <div className="signal-list">
          <h3>{t('credit.warnings')}</h3>
          {assessment.early_warning_signals.map((signal) => (
            <div key={signal.code} className="signal">
              <strong>{signal.title}</strong>
              <p>{signal.detail}</p>
            </div>
          ))}
        </div>
      )}

      {assessment.conditions.length > 0 && (
        <div className="assumption-list">
          <h3>{t('credit.conditions')}</h3>
          <ul>
            {assessment.conditions.map((condition) => (
              <li key={condition}>{condition}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function StatementResult({ result }: { result: StatementScore }) {
  const { t } = useI18n();
  const { statement_analysis: analysis } = result;

  return (
    <>
      <ScoreMeter score={result.score.final_score} category={result.score.category} />

      <p className="note">
        {analysis.source_format.toUpperCase()}
        {analysis.extraction_method ? ` · ${analysis.extraction_method}` : ''}
      </p>

      {analysis.warnings.map((warning) => (
        <ErrorBanner key={warning} message={warning} tone="warning" />
      ))}

      <RiskPanel score={result.score} />

      <div className="provenance">
        <h3>{t('credit.provenance')}</h3>
        <dl className="field-list">
          {Object.entries(analysis.derived_features).map(([key, value]) => (
            <div className="field-row" key={key}>
              <dt>{humanise(key)}</dt>
              <dd>
                {formatFeature(key, value)} <Badge tone="positive">{t('credit.fromStatement')}</Badge>
              </dd>
            </div>
          ))}
          {Object.entries(analysis.supplied_features).map(([key, entry]) => (
            <div className="field-row" key={key}>
              <dt>{humanise(key)}</dt>
              <dd>
                {formatFeature(key, entry.value)}{' '}
                <Badge tone={entry.source === 'caller' ? 'info' : 'warning'}>
                  {entry.source === 'caller' ? t('credit.fromYou') : t('credit.fromDefault')}
                </Badge>
              </dd>
            </div>
          ))}
        </dl>

        {analysis.unresolved_features.length > 0 && (
          <p className="note">
            {t('credit.unresolved')}: {analysis.unresolved_features.map(humanise).join(', ')}
          </p>
        )}
      </div>

      {result.metric_analysis && (
        <div className="metric-block">
          <h3>{t('credit.metrics')}</h3>
          <CategoryScoreBars
            scores={result.metric_analysis.category_scores}
            weights={result.metric_analysis.category_weights}
          />
          <MetricBars metrics={result.metric_analysis.metrics} />
        </div>
      )}
    </>
  );
}

export default function Credit() {
  const { t } = useI18n();
  const fileInput = useRef<HTMLInputElement>(null);

  const scored = useAsync(() => credit.score(), []);
  const metrics = useAsync(() => credit.metrics(), []);
  const serviceHealth = useAsync(() => health.scoring(), []);

  const [file, setFile] = useState<File | null>(null);
  const [overrides, setOverrides] = useState({ age: '', platform_customer_rating: '', active_platform_hours_per_week: '' });
  const [statement, setStatement] = useState<StatementScore | null>(null);
  const analyse = useAction(credit.analyzeStatement);

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    const result = await analyse.run(file, {
      age: overrides.age ? Number(overrides.age) : undefined,
      platform_customer_rating: overrides.platform_customer_rating
        ? Number(overrides.platform_customer_rating)
        : undefined,
      active_platform_hours_per_week: overrides.active_platform_hours_per_week
        ? Number(overrides.active_platform_hours_per_week)
        : undefined,
    });
    if (result) setStatement(result);
  };

  const formats = serviceHealth.data?.ingestion_formats ?? {};
  const unavailableFormats = Object.entries(formats)
    .filter(([, enabled]) => !enabled)
    .map(([name]) => name);

  return (
    <>
      <PageHeader eyebrow={t('nav.credit')} title={t('credit.title')} subtitle={t('credit.subtitle')} />

      <div className="split-grid">
        <Card title={t('credit.yourScore')} kicker={t('platforms.profile')}>
          <AsyncSection state={scored} skeletonRows={5}>
            {({ score, profile }) => (
              <>
                <ScoreMeter score={score.final_score} category={score.category} />
                {!score.ml_available && <p className="note">{t('credit.rulesOnly')}</p>}
                <RiskPanel score={score} />

                {score.explanation.length > 0 && (
                  <div className="assumption-list">
                    <h3>{t('credit.drivers')}</h3>
                    <ul>
                      {score.explanation.map((factor) => (
                        <li key={factor.feature}>
                          {humanise(factor.feature)} —{' '}
                          <Badge tone={factor.direction === 'positive' ? 'positive' : 'negative'}>
                            {factor.direction === 'positive' ? '+' : '−'}
                            {Math.abs(factor.impact).toFixed(1)}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {profile.assumptions.length > 0 && (
                  <div className="assumption-list">
                    <h3>{t('platforms.assumptions')}</h3>
                    <ul>
                      {profile.assumptions.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </AsyncSection>
        </Card>

        <Card title={t('credit.upload')} kicker={t('credit.uploadHelp')}>
          {analyse.error && <ErrorBanner message={analyse.error} />}
          {/* A format the deployment cannot parse is stated up front rather than
              discovered as a 503 after someone picks the file. */}
          {unavailableFormats.length > 0 && (
            <ErrorBanner
              tone="warning"
              message={`Not installed on this deployment: ${unavailableFormats.join(', ')}.`}
            />
          )}

          <form onSubmit={upload} className="stacked-form">
            <button
              type="button"
              className={`dropzone${file ? ' has-file' : ''}`}
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={20} strokeWidth={1.7} aria-hidden="true" />
              <strong>{file ? file.name : t('credit.uploadCta')}</strong>
              <span>{file ? `${(file.size / 1024).toFixed(0)} KB` : 'PDF, CSV, Excel, Word, TXT · 25 MB'}</span>
            </button>
            <input
              ref={fileInput}
              type="file"
              hidden
              accept=".pdf,.csv,.xlsx,.xls,.xlsm,.docx,.doc,.txt"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />

            <p className="note">
              <Info size={13} aria-hidden="true" /> {t('credit.uploadHelp')}
            </p>

            <div className="form-grid three">
              <label>
                Age
                <input
                  type="number"
                  min={18}
                  max={75}
                  value={overrides.age}
                  onChange={(event) => setOverrides((c) => ({ ...c, age: event.target.value }))}
                />
              </label>
              <label>
                {t('platforms.rating')}
                <input
                  type="number"
                  min={1}
                  max={5}
                  step={0.1}
                  value={overrides.platform_customer_rating}
                  onChange={(event) =>
                    setOverrides((c) => ({ ...c, platform_customer_rating: event.target.value }))
                  }
                />
              </label>
              <label>
                {t('platforms.hours')}
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={overrides.active_platform_hours_per_week}
                  onChange={(event) =>
                    setOverrides((c) => ({ ...c, active_platform_hours_per_week: event.target.value }))
                  }
                />
              </label>
            </div>

            <button className="primary-button wide" type="submit" disabled={!file || analyse.busy}>
              {analyse.busy ? <InlineSpinner /> : <Gauge size={15} strokeWidth={2} aria-hidden="true" />}
              {t('action.analyse')}
            </button>
          </form>

          {statement && <StatementResult result={statement} />}
        </Card>
      </div>

      <Card title={t('credit.metrics')} kicker={t('credit.metricsHelp')}>
        <AsyncSection state={metrics} skeletonRows={6}>
          {(analysis) => (
            <>
              <div className="tile-row">
                <div className="stat-tile">
                  <div className="stat-label">
                    <FileUp size={15} strokeWidth={1.8} aria-hidden="true" />
                    <span>{t('expenses.recent')}</span>
                  </div>
                  <div className="stat-value">{analysis.coverage.transactions}</div>
                  <p className="stat-hint">
                    {analysis.coverage.period_start} → {analysis.coverage.period_end} ·{' '}
                    {analysis.coverage.months_observed} months
                  </p>
                </div>
              </div>

              <CategoryScoreBars
                scores={analysis.category_scores}
                weights={analysis.category_weights}
              />

              <div className="split-grid">
                {analysis.strengths.length > 0 && (
                  <div className="assumption-list">
                    <h3>{t('credit.strengths')}</h3>
                    <ul>
                      {analysis.strengths.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {analysis.weaknesses.length > 0 && (
                  <div className="assumption-list">
                    <h3>{t('credit.weaknesses')}</h3>
                    <ul>
                      {analysis.weaknesses.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {analysis.recommended_actions.length > 0 && (
                <div className="assumption-list highlight">
                  <h3>{t('credit.actions')}</h3>
                  <ul>
                    {analysis.recommended_actions.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <MetricBars metrics={analysis.metrics} />
            </>
          )}
        </AsyncSection>
      </Card>
    </>
  );
}
