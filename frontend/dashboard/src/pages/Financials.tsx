/**
 * Business accounts: the document-ingestion pipeline pointed at a set of
 * financial statements rather than a bank statement.
 *
 * Two paths, because most small borrowers have one or the other and not both:
 * upload the accounts if they exist, otherwise estimate from GSTR-3B turnover
 * and bank flows. The estimate is labelled as one throughout, and the figures a
 * cash record genuinely cannot support come back as "not established" rather
 * than as a plausible-looking number.
 */

import { useRef, useState } from 'react';
import { Calculator, FileSpreadsheet, Plus, Trash2, Upload } from 'lucide-react';
import { financials } from '@/lib/api';
import { useAction } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { formatCompactINR, formatNumber, humanise } from '@/lib/format';
import {
  Badge,
  Card,
  ErrorBanner,
  InlineSpinner,
  PageHeader,
} from '@/components/primitives';
import type { BankRow, FinancialAnalysis, FinancialMetric, MetricSource } from '@/lib/types';

const SOURCE_TONE: Record<MetricSource, 'positive' | 'info' | 'warning' | 'neutral'> = {
  reported: 'positive',
  derived: 'info',
  estimated: 'warning',
  unavailable: 'neutral',
};

/** Ratios are plain numbers or percentages; everything else is money. */
const RATIO_SUFFIX: Record<string, string> = {
  debt_to_equity: '×',
  dscr: '×',
  pat_margin_pct: '%',
  ebitda_margin_pct: '%',
};

function MetricRow({ metric }: { metric: FinancialMetric }) {
  const { t } = useI18n();
  const suffix = RATIO_SUFFIX[metric.name];

  return (
    <div className="field-row">
      <dt title={metric.basis}>{humanise(metric.name)}</dt>
      <dd>
        <span className="metric-figure">
          {metric.value === null
            ? t('financials.unavailable')
            : suffix
              ? `${formatNumber(metric.value, 2)}${suffix}`
              : formatCompactINR(metric.value)}
        </span>
        {/* How a figure was arrived at is part of the figure. A derived EBITDA
            and a reported one are not the same evidence. */}
        <Badge tone={SOURCE_TONE[metric.source]}>{metric.source}</Badge>
      </dd>
    </div>
  );
}

function Result({ analysis }: { analysis: FinancialAnalysis }) {
  const { t } = useI18n();

  return (
    <>
      <p className="note">
        {t('financials.scale')}: <strong>{analysis.reporting_scale}</strong>
        {analysis.source_format ? ` · ${analysis.source_format}` : ''}
        {analysis.extraction_method ? ` · ${analysis.extraction_method}` : ''}
      </p>

      {analysis.warnings.map((warning) => (
        <ErrorBanner key={warning} message={warning} tone="warning" />
      ))}

      <div className="split-grid">
        <div>
          <h3 className="section-heading">{t('financials.metrics')}</h3>
          <dl className="field-list">
            {Object.values(analysis.metrics).map((metric) => (
              <MetricRow key={metric.name} metric={metric} />
            ))}
          </dl>
        </div>
        <div>
          <h3 className="section-heading">{t('financials.ratios')}</h3>
          <dl className="field-list">
            {Object.values(analysis.ratios).map((metric) => (
              <MetricRow key={metric.name} metric={metric} />
            ))}
          </dl>
        </div>
      </div>

      {analysis.unresolved.length > 0 && (
        <p className="note">
          {t('financials.unavailable')}: {analysis.unresolved.map(humanise).join(', ')}
        </p>
      )}
    </>
  );
}

const EMPTY_ROW: BankRow = { type: 'credit', amount: 0, description: '' };

export default function Financials() {
  const { t } = useI18n();
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<FinancialAnalysis | null>(null);
  const analyse = useAction(financials.analyzeDocument);

  const [turnover, setTurnover] = useState('');
  const [months, setMonths] = useState('6');
  const [rows, setRows] = useState<BankRow[]>([{ ...EMPTY_ROW }]);
  const estimate = useAction(financials.estimate);

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    const result = await analyse.run(file);
    if (result) setAnalysis(result);
  };

  const runEstimate = async (event: React.FormEvent) => {
    event.preventDefault();
    const result = await estimate.run({
      gst_taxable_turnover: turnover ? Number(turnover) : null,
      // Zero-amount rows are scaffolding the reader left behind, not data.
      bank_rows: rows.filter((row) => row.amount > 0),
      period_months: Number(months),
    });
    if (result) setAnalysis(result);
  };

  const updateRow = (index: number, patch: Partial<BankRow>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <>
      <PageHeader
        eyebrow={t('nav.financials')}
        title={t('financials.title')}
        subtitle={t('financials.subtitle')}
      />

      <div className="split-grid">
        <Card title={t('financials.upload')} kicker={t('financials.uploadHelp')}>
          {analyse.error && <ErrorBanner message={analyse.error} />}
          <form onSubmit={upload} className="stacked-form">
            <button
              type="button"
              className={`dropzone${file ? ' has-file' : ''}`}
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={20} strokeWidth={1.7} aria-hidden="true" />
              <strong>{file ? file.name : t('financials.upload')}</strong>
              <span>{file ? `${(file.size / 1024).toFixed(0)} KB` : 'PDF, Excel, CSV, Word, TXT · 25 MB'}</span>
            </button>
            <input
              ref={fileInput}
              type="file"
              hidden
              accept=".pdf,.csv,.xlsx,.xls,.xlsm,.docx,.doc,.txt"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <button className="primary-button wide" type="submit" disabled={!file || analyse.busy}>
              {analyse.busy ? (
                <InlineSpinner />
              ) : (
                <FileSpreadsheet size={15} strokeWidth={2} aria-hidden="true" />
              )}
              {t('action.analyse')}
            </button>
          </form>
        </Card>

        <Card title={t('financials.estimate')} kicker={t('financials.estimateHelp')}>
          {estimate.error && <ErrorBanner message={estimate.error} />}
          <form onSubmit={runEstimate} className="stacked-form">
            <div className="form-grid">
              <label>
                {t('financials.turnover')}
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={turnover}
                  onChange={(event) => setTurnover(event.target.value)}
                />
              </label>
              <label>
                {t('financials.periodMonths')}
                <input
                  type="number"
                  min={1}
                  max={60}
                  required
                  value={months}
                  onChange={(event) => setMonths(event.target.value)}
                />
              </label>
            </div>

            <fieldset className="row-editor">
              <legend>{t('financials.bankRows')}</legend>
              {rows.map((row, index) => (
                <div className="row-editor-line" key={index}>
                  <select
                    value={row.type}
                    aria-label={t('expenses.type')}
                    onChange={(event) =>
                      updateRow(index, { type: event.target.value as BankRow['type'] })
                    }
                  >
                    <option value="credit">{t('expenses.income')}</option>
                    <option value="debit">{t('expenses.expense')}</option>
                  </select>
                  <input
                    type="number"
                    min={0}
                    step={100}
                    placeholder={t('expenses.amount')}
                    aria-label={t('expenses.amount')}
                    value={row.amount || ''}
                    onChange={(event) => updateRow(index, { amount: Number(event.target.value) })}
                  />
                  <input
                    placeholder="Interest paid / EMI / fuel…"
                    aria-label={t('expenses.merchant')}
                    value={row.description ?? ''}
                    onChange={(event) => updateRow(index, { description: event.target.value })}
                  />
                  <button
                    type="button"
                    className="icon-button danger"
                    aria-label={t('action.remove')}
                    onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                    disabled={rows.length === 1}
                  >
                    <Trash2 size={14} strokeWidth={1.9} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="ghost-button"
                onClick={() => setRows((current) => [...current, { ...EMPTY_ROW }])}
              >
                <Plus size={14} strokeWidth={2} aria-hidden="true" />
                {t('action.add')}
              </button>
            </fieldset>

            <button className="primary-button wide" type="submit" disabled={estimate.busy}>
              {estimate.busy ? (
                <InlineSpinner />
              ) : (
                <Calculator size={15} strokeWidth={2} aria-hidden="true" />
              )}
              {t('action.analyse')}
            </button>
          </form>
        </Card>
      </div>

      {analysis && (
        <Card title={t('financials.metrics')}>
          <Result analysis={analysis} />
        </Card>
      )}
    </>
  );
}
