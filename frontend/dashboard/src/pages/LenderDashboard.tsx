/**
 * The lender's portal: the application queue, and the evidence behind each one.
 *
 * A lender sees the score, its grade, the indicative price and the early
 * warning signals -- never the applicant's raw statement or transaction list.
 * The decision they are being asked to make is about risk, and handing over the
 * underlying ledger would be a privacy cost that buys no better decision.
 */

import { useState } from 'react';
import { Check, X } from 'lucide-react';
import { loans } from '@/lib/api';
import { useAction, useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatDate, formatINR } from '@/lib/format';
import {
  AsyncSection,
  Badge,
  Card,
  ErrorBanner,
  InlineSpinner,
  PageHeader,
  StatTile,
} from '@/components/primitives';
import type { StringKey } from '@/i18n';
import type { LoanApplication, LoanStatus } from '@/lib/types';

const FILTERS: Array<{ value: LoanStatus | undefined; labelKey: StringKey }> = [
  { value: 'pending', labelKey: 'loans.status.pending' },
  { value: 'approved', labelKey: 'loans.status.approved' },
  { value: 'rejected', labelKey: 'loans.status.rejected' },
  { value: undefined, labelKey: 'lender.filterAll' },
];

const STATUS_TONE: Record<LoanStatus, 'positive' | 'negative' | 'warning'> = {
  approved: 'positive',
  rejected: 'negative',
  pending: 'warning',
};

const STATUS_KEY: Record<LoanStatus, StringKey> = {
  approved: 'loans.status.approved',
  rejected: 'loans.status.rejected',
  pending: 'loans.status.pending',
};

/** The risk tiers the scoring service can return, worst last. */
const TIER_TONE: Record<string, 'positive' | 'warning' | 'negative'> = {
  LOW: 'positive',
  MODERATE: 'positive',
  HIGH: 'warning',
  VERY_HIGH: 'negative',
};

function ApplicationCard({
  application,
  onDecided,
}: {
  application: LoanApplication;
  onDecided: () => void;
}) {
  const { t } = useI18n();
  const [note, setNote] = useState('');
  const decide = useAction(loans.decide);

  const act = async (status: 'approved' | 'rejected') => {
    const result = await decide.run(application.id, status, note || undefined);
    if (result) onDecided();
  };

  const pending = application.status === 'pending';

  return (
    <Card
      title={application.applicant_name ?? t('lender.applicant')}
      kicker={application.applicant_email ?? undefined}
      actions={<Badge tone={STATUS_TONE[application.status]}>{t(STATUS_KEY[application.status])}</Badge>}
    >
      {decide.error && <ErrorBanner message={decide.error} />}

      <div className="tile-row">
        <StatTile label={t('lender.requested')} value={formatINR(application.amount)} hint={`${application.tenor_months} months`} />
        <StatTile
          label={t('lender.score')}
          value={Math.round(application.credit_score)}
          hint={application.risk_grade ?? undefined}
          tone={application.risk_tier ? TIER_TONE[application.risk_tier] ?? 'neutral' : 'neutral'}
        />
        <StatTile
          label={t('credit.rate')}
          value={
            application.indicative_interest_rate_pct === null
              ? '—'
              : `${application.indicative_interest_rate_pct}%`
          }
          hint={application.engine_decision ?? undefined}
        />
        <StatTile
          label={t('credit.limit')}
          value={formatINR(application.max_credit_limit_inr)}
          hint={
            // The engine's own ceiling next to what was asked for is the single
            // most useful comparison on this card.
            application.max_credit_limit_inr && application.amount > application.max_credit_limit_inr
              ? 'Above the assessed ceiling'
              : undefined
          }
        />
      </div>

      <dl className="field-list">
        <div className="field-row">
          <dt>{t('loans.purpose')}</dt>
          <dd>{application.purpose ?? '—'}</dd>
        </div>
        <div className="field-row">
          <dt>{t('expenses.window')}</dt>
          <dd>{formatDate(application.created_at)}</dd>
        </div>
        {!pending && (
          <>
            <div className="field-row">
              <dt>{t('lender.decided')}</dt>
              <dd>{formatDate(application.decided_at)}</dd>
            </div>
            {application.lender_note && (
              <div className="field-row">
                <dt>{t('loans.lenderNote')}</dt>
                <dd>{application.lender_note}</dd>
              </div>
            )}
          </>
        )}
      </dl>

      {pending && (
        <div className="decision-form">
          <label>
            {t('lender.noteLabel')}
            <input
              value={note}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <div className="decision-actions">
            <button
              type="button"
              className="primary-button"
              disabled={decide.busy}
              onClick={() => void act('approved')}
            >
              {decide.busy ? <InlineSpinner /> : <Check size={15} strokeWidth={2.2} aria-hidden="true" />}
              {t('lender.approve')}
            </button>
            <button
              type="button"
              className="danger-button"
              disabled={decide.busy}
              onClick={() => void act('rejected')}
            >
              <X size={15} strokeWidth={2.2} aria-hidden="true" />
              {t('lender.reject')}
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function LenderDashboard() {
  const { t } = useI18n();
  const [filter, setFilter] = useState<LoanStatus | undefined>('pending');
  const queue = useAsync(() => loans.queue(filter), [filter]);

  return (
    <>
      <PageHeader
        eyebrow={t('auth.lenderPortal')}
        title={t('lender.title')}
        subtitle={t('lender.subtitle')}
        actions={
          <div className="segmented" role="group" aria-label={t('lender.title')}>
            {FILTERS.map((option) => (
              <button
                key={option.labelKey}
                type="button"
                className={filter === option.value ? 'active' : ''}
                onClick={() => setFilter(option.value)}
              >
                {t(option.labelKey)}
              </button>
            ))}
          </div>
        }
      />

      <AsyncSection
        state={queue}
        isEmpty={(rows) => rows.length === 0}
        emptyMessage={t('lender.empty')}
        skeletonRows={4}
      >
        {(rows) => (
          <div className="stack">
            {rows.map((application) => (
              <ApplicationCard
                key={application.id}
                application={application}
                onDecided={queue.reload}
              />
            ))}
          </div>
        )}
      </AsyncSection>
    </>
  );
}
