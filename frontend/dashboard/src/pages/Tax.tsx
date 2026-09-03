/**
 * Estimated tax on logged income.
 *
 * The two controls -- presumptive taxation and documented expenses -- are the
 * only real choice a gig worker has here, and they are mutually exclusive under
 * section 44AD, so the deductions field disables itself rather than quietly
 * being ignored.
 */

import { useState } from 'react';
import { Receipt } from 'lucide-react';
import { tax } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatINR, formatPercent } from '@/lib/format';
import { AsyncSection, Badge, Card, PageHeader, StatTile } from '@/components/primitives';

export default function Tax() {
  const { t } = useI18n();
  const [presumptive, setPresumptive] = useState(true);
  const [deductions, setDeductions] = useState('');

  const summary = useAsync(
    () => tax.summary({ presumptive, deductions: deductions ? Number(deductions) : undefined }),
    [presumptive, deductions],
  );

  return (
    <>
      <PageHeader eyebrow={t('nav.tax')} title={t('tax.title')} subtitle={t('tax.subtitle')} />

      <Card title={t('tax.title')}>
        <div className="inline-form">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={presumptive}
              onChange={(event) => setPresumptive(event.target.checked)}
            />
            {t('tax.presumptive')}
          </label>

          <label>
            {t('tax.deductions')}
            <input
              type="number"
              min={0}
              step={1000}
              value={deductions}
              // Under 44AD a deemed profit replaces itemised expenses, so this
              // field cannot apply. Disabling it says so; leaving it enabled
              // would take a number and silently discard it.
              disabled={presumptive}
              onChange={(event) => setDeductions(event.target.value)}
            />
          </label>
        </div>
      </Card>

      <AsyncSection state={summary} skeletonRows={5}>
        {(data) => (
          <>
            <div className="tile-row">
              <StatTile
                label={t('tax.total')}
                value={formatINR(data.total_tax)}
                hint={`${t('tax.year')} ${data.financial_year} · ${data.regime}`}
                tone={data.total_tax > 0 ? 'warning' : 'positive'}
              />
              <StatTile
                label={t('tax.monthly')}
                value={formatINR(data.monthly_set_aside)}
                tone="neutral"
              />
              <StatTile label={t('tax.effective')} value={formatPercent(data.effective_rate_pct)} />
              <StatTile
                label={t('tax.annualised')}
                value={formatINR(data.annualised_gross_income)}
                hint={`${t('tax.observed')}: ${formatINR(data.gross_income_observed)} over ${
                  data.observed_days
                } days`}
              />
            </div>

            <div className="split-grid">
              <Card title={t('tax.slabs')}>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th scope="col">{t('tax.slabs')}</th>
                        <th scope="col" className="numeric">
                          %
                        </th>
                        <th scope="col" className="numeric">
                          {t('tax.taxable')}
                        </th>
                        <th scope="col" className="numeric">
                          {t('tax.total')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.slabs.map((slab) => (
                        <tr key={slab.band} className={slab.taxable_in_band > 0 ? '' : 'muted-row'}>
                          <td>{slab.band}</td>
                          <td className="numeric">{slab.rate_pct}</td>
                          <td className="numeric">{formatINR(slab.taxable_in_band)}</td>
                          <td className="numeric">{formatINR(slab.tax)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              <Card title={t('tax.taxable')}>
                <dl className="field-list">
                  <div className="field-row">
                    <dt>{t('tax.annualised')}</dt>
                    <dd>{formatINR(data.annualised_gross_income)}</dd>
                  </div>
                  {data.presumptive_deduction > 0 && (
                    <div className="field-row">
                      <dt>44AD</dt>
                      <dd>− {formatINR(data.presumptive_deduction)}</dd>
                    </div>
                  )}
                  {data.deductions_claimed > 0 && (
                    <div className="field-row">
                      <dt>{t('tax.deductions')}</dt>
                      <dd>− {formatINR(data.deductions_claimed)}</dd>
                    </div>
                  )}
                  <div className="field-row">
                    <dt>{t('tax.taxable')}</dt>
                    <dd>
                      <strong>{formatINR(data.taxable_income)}</strong>
                    </dd>
                  </div>
                  <div className="field-row">
                    <dt>87A</dt>
                    <dd>− {formatINR(data.rebate)}</dd>
                  </div>
                  {data.surcharge > 0 && (
                    <div className="field-row">
                      <dt>Surcharge</dt>
                      <dd>+ {formatINR(data.surcharge)}</dd>
                    </div>
                  )}
                  <div className="field-row">
                    <dt>Cess</dt>
                    <dd>+ {formatINR(data.cess)}</dd>
                  </div>
                  <div className="field-row">
                    <dt>{t('tax.gst')}</dt>
                    <dd>
                      <Badge tone={data.gst_registration_required ? 'warning' : 'neutral'}>
                        {data.gst_registration_required ? 'Yes' : 'No'}
                      </Badge>
                    </dd>
                  </div>
                </dl>
              </Card>
            </div>

            <Card title={t('tax.notes')}>
              <ul className="note-list">
                {data.notes.map((note) => (
                  <li key={note}>
                    <Receipt size={14} strokeWidth={1.8} aria-hidden="true" />
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
