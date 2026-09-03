/**
 * The worker's home screen: stash, income baseline, score, and recent sweeps.
 *
 * Each panel loads independently. A dashboard that blanks entirely because one
 * of four services is down is worse than one that shows three panels and says
 * plainly what the fourth could not load.
 */

import { Link } from 'react-router-dom';
import { ArrowRight, Gauge, TrendingUp, Wallet } from 'lucide-react';
import { credit, money } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatDate, formatINR } from '@/lib/format';
import { ScoreMeter } from '@/components/charts';
import { AsyncSection, Badge, Card, EmptyState, PageHeader, StatTile } from '@/components/primitives';
import { useAuth } from '@/auth/AuthContext';

export default function Dashboard() {
  const { t } = useI18n();
  const { user } = useAuth();

  const dashboard = useAsync(() => money.dashboard(), []);
  const scored = useAsync(() => credit.score(), []);
  const summary = useAsync(() => money.expenseSummary(30), []);

  return (
    <>
      <PageHeader
        eyebrow={user?.name ?? ''}
        title={t('dashboard.title')}
        subtitle={t('app.tagline')}
        actions={
          <Link className="primary-button" to="/expenses">
            {t('dashboard.quickLog')}
            <ArrowRight size={14} strokeWidth={2} aria-hidden="true" />
          </Link>
        }
      />

      <div className="tile-row">
        <AsyncSection state={dashboard} skeletonRows={2}>
          {(data) => (
            <>
              <StatTile
                label={t('dashboard.stash')}
                value={formatINR(data.total_stash_balance)}
                hint={t('dashboard.stashHelp')}
                icon={<Wallet size={15} strokeWidth={1.8} aria-hidden="true" />}
                tone="positive"
              />
              <StatTile
                label={t('dashboard.baseline')}
                value={formatINR(data.income_30d_baseline)}
                icon={<TrendingUp size={15} strokeWidth={1.8} aria-hidden="true" />}
              />
            </>
          )}
        </AsyncSection>

        <AsyncSection state={summary} skeletonRows={2}>
          {(data) => (
            <StatTile
              label={t('expenses.net')}
              value={formatINR(data.net)}
              hint={`${formatINR(data.total_income)} ${t('expenses.income').toLowerCase()} · ${formatINR(
                data.total_expense,
              )} ${t('expenses.expense').toLowerCase()}`}
              tone={data.net >= 0 ? 'positive' : 'negative'}
              icon={<Gauge size={15} strokeWidth={1.8} aria-hidden="true" />}
            />
          )}
        </AsyncSection>
      </div>

      <div className="split-grid">
        <Card
          title={t('dashboard.score')}
          kicker={t('credit.subtitle')}
          actions={
            <Link className="micro-link" to="/credit">
              {t('credit.title')}
              <ArrowRight size={12} strokeWidth={2.2} aria-hidden="true" />
            </Link>
          }
        >
          <AsyncSection state={scored} skeletonRows={3}>
            {({ score, profile }) => (
              <>
                <ScoreMeter score={score.final_score} category={score.category} />

                {!score.ml_available && (
                  <p className="note">{t('credit.rulesOnly')}</p>
                )}

                {score.risk_assessment && (
                  <dl className="field-list">
                    <div className="field-row">
                      <dt>{t('credit.grade')}</dt>
                      <dd>
                        {score.risk_assessment.risk_grade.code} ·{' '}
                        {score.risk_assessment.risk_grade.label}
                      </dd>
                    </div>
                    <div className="field-row">
                      <dt>{t('credit.limit')}</dt>
                      <dd>{formatINR(score.risk_assessment.max_credit_limit_inr)}</dd>
                    </div>
                    <div className="field-row">
                      <dt>{t('credit.rate')}</dt>
                      <dd>{score.risk_assessment.indicative_interest_rate_pct}% p.a.</dd>
                    </div>
                  </dl>
                )}

                {/* Assumptions are surfaced on the home screen, not buried: a
                    score built on defaults should say so where it is first read. */}
                {profile.assumptions.length > 0 && (
                  <p className="note">
                    {profile.assumptions.length} {t('platforms.assumptions').toLowerCase()} —{' '}
                    <Link to="/platforms">{t('nav.platforms')}</Link>
                  </p>
                )}
              </>
            )}
          </AsyncSection>
        </Card>

        <Card title={t('dashboard.recentSweeps')}>
          <AsyncSection
            state={dashboard}
            emptyMessage={t('dashboard.noSweeps')}
            isEmpty={(data) => data.recent_sweeps.length === 0}
          >
            {(data) =>
              data.recent_sweeps.length === 0 ? (
                <EmptyState message={t('dashboard.noSweeps')} />
              ) : (
                <ul className="record-list">
                  {data.recent_sweeps.map((sweep) => (
                    <li key={sweep.id}>
                      <div>
                        <strong>{formatINR(sweep.sweep_amount)}</strong>
                        <span>{sweep.reason}</span>
                      </div>
                      <Badge tone="positive">{formatDate(sweep.created_at)}</Badge>
                    </li>
                  ))}
                </ul>
              )
            }
          </AsyncSection>
        </Card>
      </div>
    </>
  );
}
