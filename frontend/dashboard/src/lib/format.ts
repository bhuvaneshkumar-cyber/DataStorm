/**
 * Display formatting. One definition per format, so a rupee amount looks the
 * same on the dashboard, in the tax slabs and in a lender's queue.
 */

/** Indian digit grouping: 12,34,567 rather than 1,234,567. */
const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const inrPrecise = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatINR(amount: number | null | undefined, precise = false): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—';
  return `₹${(precise ? inrPrecise : inr).format(amount)}`;
}

/**
 * Large sums in the units Indian finance actually speaks: 1.2 Cr, 45.6 L.
 *
 * Used where a figure is being scanned rather than reconciled -- a headline
 * tile, a chart axis. Anywhere the exact rupee matters, `formatINR` is correct.
 */
export function formatCompactINR(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—';
  const magnitude = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';
  if (magnitude >= 10_000_000) return `${sign}₹${(magnitude / 10_000_000).toFixed(2)} Cr`;
  if (magnitude >= 100_000) return `${sign}₹${(magnitude / 100_000).toFixed(2)} L`;
  if (magnitude >= 1_000) return `${sign}₹${(magnitude / 1_000).toFixed(1)}K`;
  return `${sign}₹${inr.format(magnitude)}`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toFixed(digits);
}

/**
 * A date, in the reader's own locale.
 *
 * Returns an em dash rather than "Invalid Date" for anything unparseable: the
 * API can legitimately return null timestamps, and that is missing data, not an
 * error worth shouting about in the middle of a table.
 */
export function formatDate(value: string | null | undefined, locale = 'en-IN'): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Turns `payout_volatility_index` into "Payout volatility index". */
export function humanise(key: string): string {
  const spaced = key.replace(/_/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Chart axis label for a bucket key: "2026-03-15" or "2026-03". */
export function formatPeriod(period: string): string {
  const parts = period.split('-');
  const date = new Date(parts.length === 2 ? `${period}-01` : period);
  if (Number.isNaN(date.getTime())) return period;
  return parts.length === 2
    ? date.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
    : date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

export function initialsOf(name: string | null | undefined): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}
