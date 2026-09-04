/**
 * Emergency loans, from the worker's side.
 *
 * Eligibility is checked and shown before the form appears, so someone below
 * the threshold reads why and what would raise it, rather than filling in an
 * application to be refused. A rejection recorded against a name is not a
 * neutral event, and the cheapest way to avoid one is not to invite it.
 */

import { useState } from 'react';
import { HandCoins, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
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
import type { LoanStatus } from '@/lib/types';

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

export default function Loans() {
  const { t } = useI18n();
  const eligibility = useAsync(() => loans.eligibility(), []);
  const applications = useAsync(() => loans.mine(), []);
  const apply = useAction(loans.apply);

  const [form, setForm] = useState({ amount: '', tenor_months: '6', purpose: '' });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const created = await apply.run({
      amount: Number(form.amount),
      tenor_months: Number(form.tenor_months),
      ...(form.purpose ? { purpose: form.purpose } : {}),
    });
    if (!created) return;
    setForm({ amount: '', tenor_months: '6', purpose: '' });
    applications.reload();
    eligibility.reload();
  };

  return (
    <>
      <PageHeader eyebrow={t('nav.loans')} title={t('loans.title')} subtitle={t('loans.subtitle')} />

      <AsyncSection state={eligibility} skeletonRows={3}>
        {(verdict) => (
          <>
            <div className="tile-row">
              <StatTile
                label={t('dashboard.score')}
                value={Math.round(verdict.credit_score)}
                hint={`${t('loans.threshold')}: ${verdict.threshold}`}
                tone={verdict.eligible ? 'positive' : 'warning'}
              />
              <StatTile
                label={t('loans.maxAmount')}
                value={formatINR(verdict.max_amount_inr)}
                tone={verdict.eligible ? 'positive' : 'neutral'}
              />
              <StatTile label={t('loans.maxTenor')} value={`${verdict.max_tenor_months} mo`} />
              {verdict.indicative_interest_rate_pct !== null && (
                <StatTile
                  label={t('credit.rate')}
                  value={`${verdict.indicative_interest_rate_pct}%`}
                  hint={verdict.risk_grade ?? undefined}
                />
              )}
            </div>

            <Card title={verdict.eligible ? t('loans.eligible') : t('loans.notEligible')}>
              <p className="lead">{verdict.reason}</p>

              {!verdict.eligible ? (
                <div className="banner tone-warning">
                  <ShieldAlert size={16} strokeWidth={1.9} aria-hidden="true" />
                  <span>
                    <Link to="/platforms">{t('nav.platforms')}</Link> ·{' '}
                    <Link to="/expenses">{t('nav.expenses')}</Link>
                  </span>
                </div>
              ) : (
                <form className="inline-form" onSubmit={submit}>
                  {apply.error && <ErrorBanner message={apply.error} />}

                  <label>
                    {t('loans.amount')}
                    <input
                      type="number"
                      min={1000}
                      // Capped at what the assessment allows, so the form cannot
                      // ask for a figure the server has already ruled out.
                      max={Math.floor(verdict.max_amount_inr)}
                      step={500}
                      required
                      value={form.amount}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, amount: event.target.value }))
                      }
                    />
                  </label>

                  <label>
                    {t('loans.tenor')}
                    <input
                      type="number"
                      min={1}
                      max={verdict.max_tenor_months}
                      required
                      value={form.tenor_months}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, tenor_months: event.target.value }))
                      }
                    />
                  </label>

                  <label className="grow">
                    {t('loans.purpose')}
                    <input
                      value={form.purpose}
                      maxLength={200}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, purpose: event.target.value }))
                      }
                    />
                  </label>

                  <button className="primary-button" type="submit" disabled={apply.busy}>
                    {apply.busy ? (
                      <InlineSpinner />
                    ) : (
                      <HandCoins size={15} strokeWidth={2} aria-hidden="true" />
                    )}
                    {t('loans.applyCta')}
                  </button>
                </form>
              )}
            </Card>
          </>
        )}
      </AsyncSection>

      <Card title={t('loans.mine')}>
        <AsyncSection
          state={applications}
          isEmpty={(rows) => rows.length === 0}
          emptyMessage={t('loans.none')}
        >
          {(rows) => (
            <ul className="record-list">
              {rows.map((application) => (
                <li key={application.id}>
                  <div>
                    <strong>
                      {formatINR(application.amount)} · {application.tenor_months} mo
                    </strong>
                    <span>
                      {[
                        application.purpose,
                        `${t('lender.score')} ${Math.round(application.credit_score)}`,
                        application.risk_grade,
                        formatDate(application.created_at),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                    {application.lender_note && (
                      <span className="record-note">
                        {t('loans.lenderNote')}: {application.lender_note}
                      </span>
                    )}
                  </div>
                  <Badge tone={STATUS_TONE[application.status]}>
                    {t(STATUS_KEY[application.status])}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </AsyncSection>
      </Card>
    </>
  );
}
