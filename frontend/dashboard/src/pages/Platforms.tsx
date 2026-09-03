/**
 * Platform management: connect the apps a worker earns on.
 *
 * The point of the screen is the income profile at the bottom, which shows what
 * those connections add up to and -- crucially -- names every figure that had to
 * fall back to a default. That list is the shortest path a worker has to a
 * better score, so it is shown as work to do rather than hidden as a caveat.
 */

import { useState } from 'react';
import { BadgeCheck, Clock, Link2, Trash2 } from 'lucide-react';
import { platforms } from '@/lib/api';
import { useAction, useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatDate, formatINR, formatNumber } from '@/lib/format';
import {
  AsyncSection,
  Badge,
  Card,
  ErrorBanner,
  InlineSpinner,
  PageHeader,
} from '@/components/primitives';

const SUGGESTED = ['Swiggy', 'Zomato', 'Uber', 'Ola', 'Rapido', 'Blinkit', 'Zepto', 'Urban Company'];

const EMPTY_FORM = {
  platform: '',
  account_handle: '',
  customer_rating: '',
  weekly_payout: '',
  gigs_per_week: '',
  hours_per_week: '',
};

/** Empty strings mean "not stated" and must not reach the API as zero. */
function optionalNumber(value: string): number | undefined {
  if (value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export default function Platforms() {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY_FORM);

  const accounts = useAsync(() => platforms.list(), []);
  const profile = useAsync(() => platforms.incomeProfile(), []);
  const connect = useAction(platforms.connect);
  const disconnect = useAction(platforms.disconnect);

  const refresh = () => {
    accounts.reload();
    profile.reload();
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.platform.trim()) return;

    const created = await connect.run({
      platform: form.platform.trim(),
      account_handle: form.account_handle || undefined,
      customer_rating: optionalNumber(form.customer_rating),
      weekly_payout: optionalNumber(form.weekly_payout),
      gigs_per_week: optionalNumber(form.gigs_per_week),
      hours_per_week: optionalNumber(form.hours_per_week),
    });
    if (!created) return;

    setForm(EMPTY_FORM);
    refresh();
  };

  const remove = async (id: string) => {
    await disconnect.run(id);
    refresh();
  };

  return (
    <>
      <PageHeader
        eyebrow={t('nav.platforms')}
        title={t('platforms.title')}
        subtitle={t('platforms.subtitle')}
      />

      <Card title={t('platforms.connect')}>
        {connect.error && <ErrorBanner message={connect.error} />}
        {disconnect.error && <ErrorBanner message={disconnect.error} />}

        <form className="inline-form" onSubmit={submit}>
          <label>
            {t('platforms.name')}
            <input
              list="platform-options"
              required
              value={form.platform}
              onChange={(event) => setForm((current) => ({ ...current, platform: event.target.value }))}
            />
            <datalist id="platform-options">
              {SUGGESTED.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </label>

          <label>
            {t('platforms.handle')}
            <input
              value={form.account_handle}
              onChange={(event) =>
                setForm((current) => ({ ...current, account_handle: event.target.value }))
              }
            />
          </label>

          <label>
            {t('platforms.rating')}
            <input
              type="number"
              min="1"
              max="5"
              step="0.1"
              value={form.customer_rating}
              onChange={(event) =>
                setForm((current) => ({ ...current, customer_rating: event.target.value }))
              }
            />
          </label>

          <label>
            {t('platforms.weekly')}
            <input
              type="number"
              min="0"
              step="1"
              value={form.weekly_payout}
              onChange={(event) =>
                setForm((current) => ({ ...current, weekly_payout: event.target.value }))
              }
            />
          </label>

          <label>
            {t('platforms.gigs')}
            <input
              type="number"
              min="0"
              max="500"
              value={form.gigs_per_week}
              onChange={(event) =>
                setForm((current) => ({ ...current, gigs_per_week: event.target.value }))
              }
            />
          </label>

          <label>
            {t('platforms.hours')}
            <input
              type="number"
              min="0"
              max="120"
              value={form.hours_per_week}
              onChange={(event) =>
                setForm((current) => ({ ...current, hours_per_week: event.target.value }))
              }
            />
          </label>

          <button className="primary-button" type="submit" disabled={connect.busy}>
            {connect.busy ? <InlineSpinner /> : <Link2 size={15} strokeWidth={2} aria-hidden="true" />}
            {t('action.add')}
          </button>
        </form>
      </Card>

      <Card title={t('platforms.title')}>
        <AsyncSection
          state={accounts}
          isEmpty={(rows) => rows.length === 0}
          emptyMessage={t('platforms.none')}
        >
          {(rows) => (
            <ul className="record-list">
              {rows.map((account) => (
                <li key={account.id}>
                  <div>
                    <strong>{account.platform}</strong>
                    <span>
                      {[
                        account.account_handle,
                        account.weekly_payout ? `${formatINR(account.weekly_payout)}/wk` : null,
                        account.customer_rating ? `${formatNumber(account.customer_rating, 1)}★` : null,
                        account.gigs_per_week ? `${account.gigs_per_week} ${t('platforms.gigs').toLowerCase()}` : null,
                        account.hours_per_week ? `${account.hours_per_week}h` : null,
                        formatDate(account.connected_at),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </div>
                  <div className="record-actions">
                    <Badge tone={account.verified ? 'positive' : 'warning'}>
                      {account.verified ? (
                        <>
                          <BadgeCheck size={12} strokeWidth={2.2} aria-hidden="true" />
                          {t('platforms.verified')}
                        </>
                      ) : (
                        <>
                          <Clock size={12} strokeWidth={2.2} aria-hidden="true" />
                          {t('platforms.unverified')}
                        </>
                      )}
                    </Badge>
                    <button
                      type="button"
                      className="icon-button danger"
                      aria-label={`${t('action.remove')} ${account.platform}`}
                      onClick={() => void remove(account.id)}
                      disabled={disconnect.busy}
                    >
                      <Trash2 size={15} strokeWidth={1.9} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </AsyncSection>
      </Card>

      <Card title={t('platforms.profile')} kicker={t('credit.subtitle')}>
        <AsyncSection state={profile} skeletonRows={5}>
          {(data) => (
            <>
              <dl className="field-list two-column">
                <div className="field-row">
                  <dt>{t('platforms.name')}</dt>
                  <dd>{data.primary_gig_platform}</dd>
                </div>
                <div className="field-row">
                  <dt>{t('platforms.rating')}</dt>
                  <dd>{formatNumber(data.platform_customer_rating, 1)} ★</dd>
                </div>
                <div className="field-row">
                  <dt>{t('platforms.weekly')}</dt>
                  <dd>{formatINR(data.average_weekly_payout)}</dd>
                </div>
                <div className="field-row">
                  <dt>{t('platforms.gigs')}</dt>
                  <dd>{data.completed_gigs_per_week}</dd>
                </div>
                <div className="field-row">
                  <dt>{t('platforms.hours')}</dt>
                  <dd>{data.active_platform_hours_per_week}</dd>
                </div>
                <div className="field-row">
                  <dt>{t('dashboard.stash')}</dt>
                  <dd>{formatINR(data.resilience_stash_balance)}</dd>
                </div>
              </dl>

              {data.assumptions.length > 0 && (
                <div className="assumption-list">
                  <h3>{t('platforms.assumptions')}</h3>
                  <ul>
                    {data.assumptions.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </AsyncSection>
      </Card>
    </>
  );
}
