/**
 * Every chart in the app.
 *
 * Recharts is used only where a real axis earns it -- the cash-flow time series,
 * which needs ticks, a crosshair and a hover layer. The bars and meters are
 * plain HTML: a horizontal bar is a div with a width, and reaching for a chart
 * library to draw one costs control over the 4px rounded data-end and the
 * surface gap without buying anything back.
 *
 * The specs here are fixed rather than per-chart: 2px lines, >=8px markers, a
 * 10% area wash, hairline recessive gridlines, marks capped at 24px, a legend
 * whenever there are two or more series, and direct labels used sparingly.
 */

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useI18n } from '@/i18n';
import { formatCompactINR, formatINR, formatPeriod, humanise } from '@/lib/format';
import { sequentialStep, statusForScore, useVizTheme } from '@/lib/viz';
import type { CashflowPoint, CategoryTotal, MetricDetail } from '@/lib/types';

/* ------------------------------------------------------------------ */
/*  Shared pieces                                                     */
/* ------------------------------------------------------------------ */

/**
 * Identity never rests on colour alone: the swatch names the series in text
 * beside it, which is also what makes the chart readable in print and under
 * forced-colours.
 */
function Legend({ items }: { items: Array<{ label: string; color: string }> }) {
  return (
    <ul className="chart-legend">
      {items.map((item) => (
        <li key={item.label}>
          <span className="legend-swatch" style={{ background: item.color }} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string; dataKey?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label">{formatPeriod(String(label))}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="tooltip-row">
          <span className="legend-swatch" style={{ background: entry.color }} aria-hidden="true" />
          <span>{entry.name}</span>
          <strong>{formatINR(entry.value ?? 0)}</strong>
        </p>
      ))}
    </div>
  );
}

/**
 * The table behind every chart.
 *
 * Not a fallback -- a peer. It is how a screen-reader user, a colourblind
 * reader and anyone who wants the exact number all get the same data, which is
 * what lets the chart itself stay sparse.
 */
function DataTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: Array<Array<string | number>>;
}) {
  return (
    <details className="chart-table">
      <summary>{caption}</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/* ------------------------------------------------------------------ */
/*  Cash flow                                                         */
/* ------------------------------------------------------------------ */

/**
 * Income against expenses over time: two series, so categorical colour and a
 * legend. Drawn as lines with a 10% wash rather than stacked areas, because the
 * reader's question is "which is bigger this month", and a stack answers a
 * different one.
 */
export function CashflowChart({ points }: { points: CashflowPoint[] }) {
  const theme = useVizTheme();
  const { t } = useI18n();
  const [income, expense] = theme.series;

  if (!points.length) return null;

  return (
    <figure className="chart-figure">
      <Legend
        items={[
          { label: t('expenses.income'), color: income },
          { label: t('expenses.expense'), color: expense },
        ]}
      />
      <div className="chart-canvas" role="img" aria-label={t('expenses.cashflow')}>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            {/* Horizontal only, hairline, solid: gridlines orient the eye and
                must not compete with the data for ink. */}
            <CartesianGrid stroke={theme.grid} strokeWidth={1} vertical={false} />
            <XAxis
              dataKey="period"
              tickFormatter={formatPeriod}
              tick={{ fill: theme.textSecondary, fontSize: 11 }}
              stroke={theme.axis}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis
              tickFormatter={(value: number) => formatCompactINR(value)}
              tick={{ fill: theme.textSecondary, fontSize: 11 }}
              stroke={theme.axis}
              tickLine={false}
              axisLine={false}
              width={62}
            />
            <Tooltip
              content={<ChartTooltip />}
              cursor={{ stroke: theme.axis, strokeWidth: 1 }}
            />
            <Area
              type="monotone"
              dataKey="income"
              name={t('expenses.income')}
              stroke="none"
              fill={income}
              fillOpacity={0.1}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="expense"
              name={t('expenses.expense')}
              stroke="none"
              fill={expense}
              fillOpacity={0.1}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="income"
              name={t('expenses.income')}
              stroke={income}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              // The 2px ring in the surface colour keeps a dot legible where the
              // two series cross, and enlarges its hover target at the same time.
              dot={{ r: 4, fill: income, stroke: theme.surface, strokeWidth: 2 }}
              activeDot={{ r: 5, fill: income, stroke: theme.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="expense"
              name={t('expenses.expense')}
              stroke={expense}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={{ r: 4, fill: expense, stroke: theme.surface, strokeWidth: 2 }}
              activeDot={{ r: 5, fill: expense, stroke: theme.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <DataTable
        caption={t('expenses.cashflow')}
        columns={[t('expenses.window'), t('expenses.income'), t('expenses.expense'), t('expenses.net')]}
        rows={points.map((point) => [
          formatPeriod(point.period),
          formatINR(point.income),
          formatINR(point.expense),
          formatINR(point.net),
        ])}
      />
    </figure>
  );
}

/* ------------------------------------------------------------------ */
/*  Category breakdown                                                */
/* ------------------------------------------------------------------ */

/**
 * Where the money goes: one measure across named categories, so horizontal bars
 * on a single-hue ramp rather than a donut. Category names are long and the
 * reader is comparing magnitudes; both point away from a pie.
 *
 * A single series needs no legend -- the heading already says what is plotted --
 * and each bar carries its own value at the tip.
 */
export function CategoryBars({
  categories,
  limit = 7,
  label,
}: {
  categories: CategoryTotal[];
  limit?: number;
  label: string;
}) {
  const theme = useVizTheme();

  if (!categories.length) return null;

  // Past the cap the tail folds into one bar rather than sprouting more colours.
  const visible = categories.slice(0, limit);
  const tail = categories.slice(limit);
  const rows = tail.length
    ? [
        ...visible,
        {
          category: `Other (${tail.length})`,
          total: tail.reduce((sum, item) => sum + item.total, 0),
          share_pct: tail.reduce((sum, item) => sum + item.share_pct, 0),
        },
      ]
    : visible;

  const largest = Math.max(...rows.map((row) => row.total), 1);

  return (
    <figure className="chart-figure">
      <ul className="bar-list" aria-label={label}>
        {rows.map((row, index) => (
          <li key={row.category}>
            <div className="bar-head">
              <span className="bar-name" title={row.category}>
                {row.category}
              </span>
              <span className="bar-value">
                {formatINR(row.total)}
                <em>{row.share_pct.toFixed(1)}%</em>
              </span>
            </div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${Math.max((row.total / largest) * 100, 1.5)}%`,
                  background: sequentialStep(theme, index, rows.length),
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/* ------------------------------------------------------------------ */
/*  Meters                                                            */
/* ------------------------------------------------------------------ */

/**
 * A single value against its ceiling: a meter, not a gauge dial and not a
 * one-slice pie. The fill carries severity and the track is a lighter step of
 * the same ramp, so the state reads across the whole bar.
 */
export function ScoreMeter({
  score,
  max = 800,
  category,
}: {
  score: number;
  max?: number;
  category?: string;
}) {
  const theme = useVizTheme();
  const { color, band } = statusForScore(theme, (score / max) * 100);
  const pct = Math.min(Math.max((score / max) * 100, 0), 100);

  return (
    <div className="meter">
      <div className="meter-figure">
        <span className="hero-number">{Math.round(score)}</span>
        <span className="meter-max">/ {max}</span>
        {/* The band is written out beside the colour, never signalled by it alone. */}
        <span className="meter-band" style={{ color }}>
          {category ?? band}
        </span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-valuenow={Math.round(score)}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={`Credit score ${Math.round(score)} of ${max}`}
      >
        <div className="meter-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Metric breakdown                                                  */
/* ------------------------------------------------------------------ */

/**
 * Fourteen metrics, each scored 0-100 with a named band.
 *
 * Sorted weakest first: the reader's question is "what is holding me back", and
 * the answer belongs at the top rather than at the end of a scroll.
 */
export function MetricBars({ metrics }: { metrics: Record<string, MetricDetail> }) {
  const theme = useVizTheme();
  const rows = Object.values(metrics).sort((a, b) => a.score - b.score);

  if (!rows.length) return null;

  return (
    <ul className="bar-list metric-list">
      {rows.map((metric) => {
        const { color } = statusForScore(theme, metric.score);
        return (
          <li key={metric.name}>
            <div className="bar-head">
              <span className="bar-name" title={metric.description}>
                {humanise(metric.name)}
              </span>
              <span className="bar-value">
                {/* Status is stated in words as well as colour. */}
                <span className="metric-band" style={{ color }}>
                  {metric.status}
                </span>
                <em>{Math.round(metric.score)}/100</em>
              </span>
            </div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${Math.max(metric.score, 1.5)}%`, background: color }}
              />
            </div>
            <p className="bar-caption">{metric.description}</p>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The four weighted categories behind the composite score.
 *
 * The weight is shown next to each: a category scoring 80 at 15% weight and one
 * scoring 60 at 35% weight are not comparable, and the reader cannot tell that
 * from bar length alone.
 */
export function CategoryScoreBars({
  scores,
  weights,
}: {
  scores: Record<string, number>;
  weights: Record<string, number>;
}) {
  const theme = useVizTheme();
  const rows = Object.entries(scores).sort(([, a], [, b]) => b - a);

  return (
    <ul className="bar-list">
      {rows.map(([name, score]) => {
        const { color, band } = statusForScore(theme, score);
        const weight = weights[name];
        return (
          <li key={name}>
            <div className="bar-head">
              <span className="bar-name">{humanise(name)}</span>
              <span className="bar-value">
                <span className="metric-band" style={{ color }}>
                  {band}
                </span>
                <em>
                  {Math.round(score)}/100
                  {weight !== undefined && ` · ${Math.round(weight * 100)}% weight`}
                </em>
              </span>
            </div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${Math.max(score, 1.5)}%`, background: color }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
