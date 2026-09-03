/**
 * The small shared pieces every screen is built from.
 *
 * Grouped in one file rather than one-per-file: they are a handful of lines
 * each, they are always imported together, and fourteen two-line modules is
 * more filesystem than structure.
 */

import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { useI18n } from '@/i18n';

/* ------------------------------------------------------------------ */
/*  Layout                                                            */
/* ------------------------------------------------------------------ */

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && (
          <p className="eyebrow">
            <span className="eyebrow-dot" aria-hidden="true" />
            {eyebrow}
          </p>
        )}
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  kicker,
  actions,
  children,
  className = '',
}: {
  title?: string;
  kicker?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`.trim()}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {kicker && <p className="card-kicker">{kicker}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Data display                                                      */
/* ------------------------------------------------------------------ */

export function StatTile({
  label,
  value,
  hint,
  tone = 'neutral',
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning';
  icon?: React.ReactNode;
}) {
  return (
    <div className={`stat-tile tone-${tone}`}>
      <div className="stat-label">
        {icon}
        <span>{label}</span>
      </div>
      <div className="stat-value">{value}</div>
      {hint && <p className="stat-hint">{hint}</p>}
    </div>
  );
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning' | 'info';
}) {
  return <span className={`badge tone-${tone}`}>{children}</span>;
}

/* ------------------------------------------------------------------ */
/*  States                                                            */
/* ------------------------------------------------------------------ */

export function EmptyState({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      <Inbox size={22} strokeWidth={1.6} aria-hidden="true" />
      <p>{message}</p>
      {action}
    </div>
  );
}

/**
 * An error the user can act on.
 *
 * `onRetry` is what turns a dead end into a recoverable one, and it matters
 * most for the case this app hits most: a service that is briefly down.
 */
export function ErrorBanner({
  message,
  onRetry,
  tone = 'negative',
}: {
  message: string;
  onRetry?: () => void;
  tone?: 'negative' | 'warning';
}) {
  const { t } = useI18n();
  return (
    <div className={`banner tone-${tone}`} role="alert">
      <AlertTriangle size={16} strokeWidth={1.9} aria-hidden="true" />
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="banner-action" onClick={onRetry}>
          <RefreshCw size={13} strokeWidth={2} aria-hidden="true" />
          {t('action.retry')}
        </button>
      )}
    </div>
  );
}

/** Rendered while a section loads. Skeletons, not a spinner, so the layout does not jump. */
export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton" style={{ width: `${100 - index * 12}%` }} />
      ))}
    </div>
  );
}

export function InlineSpinner({ label }: { label?: string }) {
  return (
    <span className="inline-spinner">
      <Loader2 size={14} className="spin" aria-hidden="true" />
      {label}
    </span>
  );
}

/**
 * Wraps a section in the three states every fetch can be in.
 *
 * Every screen routes its loading, error and empty handling through this, so a
 * failed request looks the same everywhere and no page can quietly forget to
 * handle one of them.
 */
export function AsyncSection<T>({
  state,
  children,
  emptyMessage,
  isEmpty,
  skeletonRows,
}: {
  state: {
    data: T | null;
    error: string | null;
    loading: boolean;
    unavailable: boolean;
    reload: () => void;
  };
  children: (data: T) => React.ReactNode;
  emptyMessage?: string;
  isEmpty?: (data: T) => boolean;
  skeletonRows?: number;
}) {
  const { t } = useI18n();

  if (state.loading && state.data === null) return <CardSkeleton rows={skeletonRows} />;

  if (state.error && state.data === null) {
    return (
      <ErrorBanner
        message={state.unavailable ? `${t('state.unavailable')} ${state.error}` : state.error}
        onRetry={state.reload}
        tone={state.unavailable ? 'warning' : 'negative'}
      />
    );
  }

  if (state.data === null) return <EmptyState message={emptyMessage ?? t('state.empty')} />;
  if (isEmpty?.(state.data)) return <EmptyState message={emptyMessage ?? t('state.empty')} />;

  return <>{children(state.data)}</>;
}
