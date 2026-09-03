/**
 * The expense tracker: log income and spending, and see what it adds up to.
 *
 * Logging is on the same screen as the charts rather than behind a modal,
 * because the two are one loop -- you add an entry to see the chart move -- and
 * splitting them makes the first entry feel like paperwork.
 */

import { useState } from 'react';
import { Check, PiggyBank, Plus } from 'lucide-react';
import { money } from '@/lib/api';
import { useAction, useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatDate, formatINR } from '@/lib/format';
import { CashflowChart, CategoryBars } from '@/components/charts';
import {
  AsyncSection,
  Badge,
  Card,
  EmptyState,
  ErrorBanner,
  InlineSpinner,
  PageHeader,
  StatTile,
} from '@/components/primitives';
import type { SweepDecision, TransactionType } from '@/lib/types';

/** Offered as suggestions, not enforced: the field accepts any text. */
const EXPENSE_CATEGORIES = ['Fuel', 'Food', 'Rent', 'Vehicle', 'Phone', 'Medical', 'Family', 'Other'];
const INCOME_CATEGORIES = ['Swiggy', 'Zomato', 'Uber', 'Ola', 'Rapido', 'Freelance', 'Other'];

const WINDOWS = [30, 90, 180, 365];

export default function Expenses() {
  const { t } = useI18n();
  const [windowDays, setWindowDays] = useState(90);

  const summary = useAsync(() => money.expenseSummary(windowDays), [windowDays]);
  const transactions = useAsync(() => money.transactions(25), []);

  const [form, setForm] = useState({
    amount: '',
    transaction_type: 'debit' as TransactionType,
    merchant: '',
    category: '',
  });
  // The sweep decision from the last logged entry. Held so an eligible one can
  // be authorized: the round-up is advice until someone acts on it, and the API
  // deliberately keeps ingesting and authorizing as two separate steps.
  const [pendingSweep, setPendingSweep] = useState<SweepDecision | null>(null);
  const [swept, setSwept] = useState<string | null>(null);
  const log = useAction(money.logTransaction);
  const authorize = useAction(money.authorizeSweep);

  const isIncome = form.transaction_type === 'platform_payout';

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const amount = Number(form.amount);
    if (!Number.isFinite(amount) || amount <= 0) return;

    const created = await log.run({
      amount,
      transaction_type: form.transaction_type,
      ...(form.merchant ? { merchant: form.merchant } : {}),
      ...(form.category ? { category: form.category } : {}),
    });
    if (!created) return;

    // The round-up this entry produced is the immediate feedback that makes the
    // savings mechanic legible. Without it, logging an expense feels inert.
    setPendingSweep(created.sweep_decision);
    setSwept(null);
    setForm({ amount: '', transaction_type: form.transaction_type, merchant: '', category: '' });
    summary.reload();
    transactions.reload();
  };

  const authorizeSweep = async (amount: number) => {
    const sweep = await authorize.run(amount, 'Round-up sweep authorized from the expense tracker');
    if (!sweep) return;
    setPendingSweep(null);
    setSwept(`${t('expenses.sweepDone')}: ${formatINR(sweep.sweep_amount)}`);
  };

  return (
    <>
      <PageHeader
        eyebrow={t('nav.expenses')}
        title={t('expenses.title')}
        subtitle={t('expenses.subtitle')}
      />

      <Card title={t('expenses.log')}>
        {log.error && <ErrorBanner message={log.error} />}
        {authorize.error && <ErrorBanner message={authorize.error} />}

        {swept && (
          <div className="banner tone-positive" role="status">
            <Check size={15} strokeWidth={2} aria-hidden="true" />
            <span>{swept}</span>
          </div>
        )}

        {pendingSweep && !swept && (
          <div className={`banner tone-${pendingSweep.eligible ? 'positive' : 'warning'}`} role="status">
            <PiggyBank size={15} strokeWidth={2} aria-hidden="true" />
            <span>
              {t('expenses.sweepPending')}: {formatINR(pendingSweep.amount)} — {pendingSweep.reason}
            </span>
            {/* Only offered when the engine says the sweep clears the threshold
                and the mandate cap; otherwise the reason above explains why not. */}
            {pendingSweep.eligible && (
              <button
                type="button"
                className="banner-action"
                disabled={authorize.busy}
                onClick={() => void authorizeSweep(pendingSweep.amount)}
              >
                {t('expenses.authorizeSweep')}
              </button>
            )}
          </div>
        )}

        <form className="inline-form" onSubmit={submit}>
          <label>
            {t('expenses.type')}
            <select
              value={form.transaction_type}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  transaction_type: event.target.value as TransactionType,
                  category: '',
                }))
              }
            >
              <option value="debit">{t('expenses.typeExpense')}</option>
              <option value="platform_payout">{t('expenses.typeIncome')}</option>
            </select>
          </label>

          <label>
            {t('expenses.amount')}
            <input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={form.amount}
              onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))}
            />
          </label>

          <label>
            {t('expenses.category')}
            {/* A datalist rather than a select: the suggestions help, but a
                worker with a category we did not think of can still type it. */}
            <input
              list="category-options"
              value={form.category}
              onChange={(event) =>
                setForm((current) => ({ ...current, category: event.target.value }))
              }
            />
            <datalist id="category-options">
              {(isIncome ? INCOME_CATEGORIES : EXPENSE_CATEGORIES).map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </label>

          <label>
            {t('expenses.merchant')}
            <input
              value={form.merchant}
              onChange={(event) =>
                setForm((current) => ({ ...current, merchant: event.target.value }))
              }
            />
          </label>

          <button className="primary-button" type="submit" disabled={log.busy}>
            {log.busy ? <InlineSpinner /> : <Plus size={15} strokeWidth={2} aria-hidden="true" />}
            {t('action.add')}
          </button>
        </form>
      </Card>

      <Card
        title={t('expenses.cashflow')}
        actions={
          <div className="segmented" role="group" aria-label={t('expenses.window')}>
            {WINDOWS.map((days) => (
              <button
                key={days}
                type="button"
                className={windowDays === days ? 'active' : ''}
                onClick={() => setWindowDays(days)}
              >
                {days}d
              </button>
            ))}
          </div>
        }
      >
        <AsyncSection
          state={summary}
          skeletonRows={4}
          isEmpty={(data) => data.transaction_count === 0}
          emptyMessage={t('state.empty')}
        >
          {(data) => (
            <>
              <div className="tile-row">
                <StatTile label={t('expenses.income')} value={formatINR(data.total_income)} tone="positive" />
                <StatTile label={t('expenses.expense')} value={formatINR(data.total_expense)} tone="negative" />
                <StatTile
                  label={t('expenses.net')}
                  value={formatINR(data.net)}
                  tone={data.net >= 0 ? 'positive' : 'negative'}
                />
              </div>
              {/* Daily buckets get noisy past a quarter; monthly reads better
                  over a long window and the underlying totals are identical. */}
              <CashflowChart points={windowDays > 90 ? data.monthly : data.daily} />
            </>
          )}
        </AsyncSection>
      </Card>

      <div className="split-grid">
        <Card title={t('expenses.byCategory')}>
          <AsyncSection
            state={summary}
            isEmpty={(data) => data.expense_categories.length === 0}
            emptyMessage={t('state.empty')}
          >
            {(data) => <CategoryBars categories={data.expense_categories} label={t('expenses.byCategory')} />}
          </AsyncSection>
        </Card>

        <Card title={t('expenses.bySource')}>
          <AsyncSection
            state={summary}
            isEmpty={(data) => data.income_sources.length === 0}
            emptyMessage={t('state.empty')}
          >
            {(data) => <CategoryBars categories={data.income_sources} label={t('expenses.bySource')} />}
          </AsyncSection>
        </Card>
      </div>

      <Card title={t('expenses.recent')}>
        <AsyncSection
          state={transactions}
          isEmpty={(rows) => rows.length === 0}
          emptyMessage={t('state.empty')}
        >
          {(rows) =>
            rows.length === 0 ? (
              <EmptyState message={t('state.empty')} />
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('expenses.window')}</th>
                      <th scope="col">{t('expenses.type')}</th>
                      <th scope="col">{t('expenses.category')}</th>
                      <th scope="col">{t('expenses.merchant')}</th>
                      <th scope="col" className="numeric">
                        {t('expenses.amount')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td>{formatDate(row.timestamp)}</td>
                        <td>
                          <Badge tone={row.transaction_type === 'platform_payout' ? 'positive' : 'neutral'}>
                            {row.transaction_type === 'platform_payout'
                              ? t('expenses.income')
                              : t('expenses.expense')}
                          </Badge>
                        </td>
                        <td>{row.category ?? '—'}</td>
                        <td>{row.merchant ?? '—'}</td>
                        <td className="numeric">{formatINR(row.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </AsyncSection>
      </Card>
    </>
  );
}
