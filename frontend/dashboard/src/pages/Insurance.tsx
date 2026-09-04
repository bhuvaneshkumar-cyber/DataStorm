/**
 * Micro-insurance advice, ranked by the exposures a person's work carries.
 *
 * Every card states why it placed where it did. That is the whole product here:
 * a ranked list without reasons is a sales page, and this is not selling
 * anything -- nothing is bound and no premium is collected.
 */

import { Umbrella } from 'lucide-react';
import { Link } from 'react-router-dom';
import { insurance } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatINR, formatNumber } from '@/lib/format';
import { AsyncSection, Badge, Card, PageHeader, StatTile } from '@/components/primitives';
import type { InsuranceOption } from '@/lib/types';
import type { StringKey } from '@/i18n';

const URGENCY_TONE = {
  essential: 'negative',
  recommended: 'warning',
  optional: 'neutral',
} as const;

const URGENCY_KEY: Record<InsuranceOption['urgency'], StringKey> = {
  essential: 'insurance.essential',
  recommended: 'insurance.recommended',
  optional: 'insurance.optional',
};

export default function Insurance() {
  const { t } = useI18n();
  const advice = useAsync(() => insurance.recommendations(), []);

  return (
    <>
      <PageHeader
        eyebrow={t('nav.insurance')}
        title={t('insurance.title')}
        subtitle={t('insurance.subtitle')}
      />

      <AsyncSection state={advice} skeletonRows={5}>
        {({ recommendation, profile }) => (
          <>
            <div className="tile-row">
              <StatTile
                label={t('dashboard.score')}
                value={Math.round(recommendation.credit_score)}
                hint={recommendation.risk_tier}
              />
              <StatTile
                label={t('insurance.runway')}
                value={`${formatNumber(recommendation.savings_runway_weeks, 1)} wk`}
                tone={recommendation.savings_runway_weeks < 2 ? 'warning' : 'positive'}
                hint={formatINR(profile.resilience_stash_balance)}
              />
              <StatTile
                label={t('auth.employment')}
                value={recommendation.employment_type ?? recommendation.matched_exposure_profile}
                hint={
                  recommendation.employment_type
                    ? undefined
                    : t('platforms.assumptions')
                }
              />
            </div>

            <div className="card-grid">
              {recommendation.recommendations.map((option) => (
                <Card key={option.code} title={option.title}>
                  <div className="option-head">
                    {/* Urgency is written out; the tone colour only reinforces it. */}
                    <Badge tone={URGENCY_TONE[option.urgency]}>{t(URGENCY_KEY[option.urgency])}</Badge>
                    <span className="option-priority">
                      {t('insurance.priority')} {Math.round(option.priority * 100)}%
                    </span>
                  </div>

                  <p className="lead">{option.description}</p>

                  <div className="assumption-list">
                    <h3>{t('insurance.why')}</h3>
                    <ul>
                      {option.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>

                  <dl className="field-list">
                    <div className="field-row">
                      <dt>{t('insurance.premium')}</dt>
                      <dd>
                        {option.indicative_monthly_premium_inr ? (
                          `${formatINR(option.indicative_monthly_premium_inr[0])} – ${formatINR(
                            option.indicative_monthly_premium_inr[1],
                          )}`
                        ) : (
                          <>
                            {option.premium_pct_of_weekly_payout[0]}–{option.premium_pct_of_weekly_payout[1]}%{' '}
                            {t('insurance.premiumPctSuffix')} · <Link to="/expenses">{t('dashboard.quickLog')}</Link>
                          </>
                        )}
                      </dd>
                    </div>
                  </dl>
                </Card>
              ))}
            </div>

            <Card title={t('tax.notes')}>
              <ul className="note-list">
                {recommendation.notes.map((note) => (
                  <li key={note}>
                    <Umbrella size={14} strokeWidth={1.8} aria-hidden="true" />
                    {note}
                  </li>
                ))}
              </ul>
            </Card>
          </>
        )}
      </AsyncSection>
    </>
  );
}
