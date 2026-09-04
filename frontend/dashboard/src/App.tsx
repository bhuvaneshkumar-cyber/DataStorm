import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  CreditCard,
  Gauge,
  HandCoins,
  Info,
  RotateCcw,
  ShieldCheck,
  TrendingUp,
  Wallet,
  X,
} from 'lucide-react';
import { STASH_GOAL, WORKER_PLATFORM_PROFILE } from '@/config';
import {
  fetchCreditScore,
  fetchDashboard,
  type CreditScoreResponse,
  type DashboardStats,
  type RecentSweep,
} from '@/lib/api';
import Sidebar from '@/components/Sidebar';

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function formatINR(amount: number) {
  return `₹${Math.round(amount).toLocaleString('en-IN')}`;
}

function formatDate(iso: string | null) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('en-IN');
}

/** SHAP returns raw column names; the UI shows what they mean. */
const FEATURE_LABELS: Record<string, string> = {
  age: 'Age',
  primary_gig_platform: 'Primary platform',
  platform_customer_rating: 'Customer rating',
  completed_gigs_per_week: 'Gigs completed weekly',
  average_weekly_payout: 'Average weekly payout',
  payout_volatility_index: 'Income volatility',
  active_platform_hours_per_week: 'Hours worked weekly',
  resilience_stash_balance: 'Resilience stash balance',
};

/** Sweeps recorded in the current calendar month. */
function sweepsThisMonth(sweeps: RecentSweep[]) {
  const now = new Date();
  const current = sweeps.filter((sweep) => {
    if (!sweep.created_at) return false;
    const date = new Date(sweep.created_at);
    return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear();
  });
  return {
    count: current.length,
    total: current.reduce((sum, sweep) => sum + sweep.sweep_amount, 0),
  };
}

/* ------------------------------------------------------------------ */
/*  Sweep Row                                                         */
/* ------------------------------------------------------------------ */

function SweepRow({ sweep }: { sweep: RecentSweep }) {
  return (
    <div className="sweep-row" role="listitem" data-testid={`row-sweep-${sweep.id}`}>
      <div className="source-icon source-freelance" aria-hidden="true">
        <HandCoins size={15} strokeWidth={1.9} />
      </div>
      <div className="sweep-source">
        <div className="sweep-name" data-testid={`text-sweep-source-${sweep.id}`}>
          {sweep.reason}
        </div>
        <div className="sweep-date">{formatDate(sweep.created_at)}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div className="sweep-amount" data-testid={`text-sweep-amount-${sweep.id}`}>
          +{formatINR(sweep.sweep_amount)}
        </div>
        <div className="completed" data-testid={`status-sweep-${sweep.id}`}>
          Completed
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading                                                           */
/* ------------------------------------------------------------------ */

function LoadingState() {
  return (
    <div className="loading-grid" aria-label="Loading financial snapshot" data-testid="state-loading">
      {[1, 2, 3, 4].map((item) => (
        <div className="card loading-card" key={item}>
          <div className="skeleton" style={{ width: '40%', height: 12 }} />
          <div className="skeleton" style={{ width: '68%', height: 36, marginTop: 26 }} />
          <div className="skeleton" style={{ width: '92%', height: 10, marginTop: 22 }} />
          <div className="skeleton" style={{ width: '78%', height: 10, marginTop: 9 }} />
          <div className="skeleton" style={{ width: '100%', height: 8, marginTop: 31 }} />
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Modal                                                             */
/* ------------------------------------------------------------------ */

type ModalContent = { title: string; intro: string; highlight: string; bullets: string[] };

function Modal({ content, onClose }: { content: ModalContent; onClose: () => void }) {
  return (
    <div
      className="modal-scrim"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <button
          className="icon-button modal-close"
          type="button"
          aria-label="Close details"
          data-testid="button-close-modal"
          onClick={onClose}
        >
          <X size={17} />
        </button>
        <h2 id="modal-title">{content.title}</h2>
        <p>{content.intro}</p>
        <div className="modal-highlight">{content.highlight}</div>
        <ul className="modal-list">
          {content.bullets.map((bullet) => (
            <li key={bullet}>
              <Check size={14} />
              {bullet}
            </li>
          ))}
        </ul>
        <button
          className="primary-button"
          type="button"
          data-testid="button-modal-done"
          onClick={onClose}
          style={{ marginTop: 22 }}
        >
          Got it
        </button>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Home (main dashboard page)                                        */
/* ------------------------------------------------------------------ */

function Home() {
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null);
  const [score, setScore] = useState<CreditScoreResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [modal, setModal] = useState<'stash' | 'score' | null>(null);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const brandRef = useRef<HTMLDivElement>(null);

  // Every number on this page comes from one of the two services. A failure is
  // surfaced, never papered over with placeholder figures.
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setScoreError(null);

    let stats: DashboardStats;
    try {
      stats = await fetchDashboard();
      setDashboard(stats);
    } catch (err) {
      setDashboard(null);
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
      return;
    }

    // The scoring model needs the worker's financial position, which only the
    // financial API knows — so it is scored against the balance we just loaded.
    try {
      setScore(
        await fetchCreditScore({
          ...WORKER_PLATFORM_PROFILE,
          average_weekly_payout: Math.max(stats.income_30d_baseline, 1),
          resilience_stash_balance: stats.total_stash_balance,
        }),
      );
    } catch (err) {
      setScore(null);
      setScoreError(err instanceof Error ? err.message : String(err));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stash = dashboard?.total_stash_balance ?? 0;
  const pending = dashboard?.pending_contributions ?? 0;
  const sweeps = dashboard?.recent_sweeps ?? [];
  const targetProgress = Math.min((stash / STASH_GOAL) * 100, 100);
  const month = sweepsThisMonth(sweeps);

  const modalContent: ModalContent | null =
    modal === 'stash'
      ? {
          title: 'Your Stash is working quietly',
          intro:
            'This is money set aside for the uneven moments — a slower week, an unexpected repair, or simply a little more breathing room.',
          highlight: `${formatINR(stash)} ready when you need it`,
          bullets: [
            'Your Stash is separate from everyday spending.',
            'Automatic sweeps round up debits and skim a share of above-average payouts.',
            `${formatINR(pending)} is queued for your next sweep.`,
            `You are ${Math.round(targetProgress)}% of the way to your ${formatINR(STASH_GOAL)} cushion goal.`,
          ],
        }
      : modal === 'score' && score
        ? {
            title: 'A fuller picture of credit',
            intro:
              'Your Gig Credit Score is designed for income that does not arrive on the same day every month. It blends a transparent rule score with a model trained on gig-work patterns.',
            highlight: `${Math.round(score.final_score)} · ${score.category}`,
            bullets: [
              `Rule engine: ${Math.round(score.rule_score)} out of 800.`,
              score.ml_available
                ? `Model: ${Math.round(score.ml_score ?? 0)} out of 800, blended at 60% weight.`
                : 'The model is unavailable, so this score is 100% rule-based.',
              `Confidence ${(score.confidence * 100).toFixed(0)}%, scored in ${score.latency_ms} ms.`,
            ],
          }
        : null;

  return (
    <div className="dashboard-shell">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} triggerRef={brandRef} />

      {/* ---- Header ---- */}
      <header className="app-header">
        <div className="header-inner">
          <div
            className="brand-mark"
            ref={brandRef}
            role="button"
            tabIndex={0}
            data-testid="text-brand"
            aria-label={sidebarOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((open) => !open)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setSidebarOpen((open) => !open);
              }
            }}
          >
            <div className="brand-symbol" aria-hidden="true">
              <ShieldCheck size={18} strokeWidth={2.5} />
            </div>
            <span className="brand-word">Bryn</span>
          </div>
          <div className="header-greeting">
            <strong>Your financial resilience</strong>
            <span>Micro-savings and gig credit, from live account data</span>
          </div>
          <div className="header-actions">
            <button
              className="icon-button"
              type="button"
              aria-label="Refresh snapshot"
              data-testid="button-refresh"
              onClick={() => void load()}
            >
              <RotateCcw size={18} strokeWidth={1.8} />
            </button>
          </div>
        </div>
      </header>

      {/* ---- Main content ---- */}
      <main className="dashboard-main">
        <div className="page-title">
          <div className="eyebrow">
            <span className="eyebrow-dot" /> Personal financial space
          </div>
          <h1>Your resilience, at a glance.</h1>
          <p>A calmer way to build room for whatever comes next.</p>
        </div>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <div className="error-state" role="alert" data-testid="state-error">
            <CircleAlert size={27} strokeWidth={1.7} />
            <h2>We couldn&apos;t load your savings</h2>
            <p data-testid="text-error-detail">{error}</p>
            <button
              className="primary-button"
              type="button"
              data-testid="button-retry"
              onClick={() => void load()}
            >
              <RotateCcw size={14} /> Try again
            </button>
          </div>
        ) : (
          <div className="layout-grid">
            {/* ---- Financial overview ---- */}
            <section aria-labelledby="overview-heading">
              <div className="card-head" style={{ paddingLeft: 0, paddingTop: 0, paddingBottom: 13 }}>
                <div>
                  <h2 className="card-title" id="overview-heading">
                    Financial overview
                  </h2>
                  <p className="card-kicker">A clear view of the habits making you stronger.</p>
                </div>
                <Gauge size={17} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
              </div>
              <div className="overview-grid">
                {/* Stash card */}
                <article className="card stash-card stagger-1" data-testid="card-stash">
                  <div className="card-head">
                    <div>
                      <h3 className="card-title">Your Stash</h3>
                      <p className="card-kicker">Your quiet safety net</p>
                    </div>
                    <Wallet size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
                  </div>
                  <div className="stash-content">
                    <div className="money-label">Available buffer</div>
                    <div className="money-value" data-testid="text-stash-amount">
                      {formatINR(stash)}
                    </div>
                    <div className="money-delta" data-testid="text-stash-pending">
                      <TrendingUp size={13} /> {formatINR(pending)} queued for your next sweep
                    </div>
                    <p className="stash-note">
                      You are building a buffer for the days work gets a little quieter.
                    </p>
                    <div className="stash-footer">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          className="progress-track"
                          aria-label={`${Math.round(targetProgress)}% of your Stash goal`}
                        >
                          <div className="stash-progress" style={{ width: `${targetProgress}%` }} />
                        </div>
                        <div className="progress-caption" data-testid="text-stash-progress">
                          {Math.round(targetProgress)}% of {formatINR(STASH_GOAL)} buffer goal
                        </div>
                      </div>
                      <button
                        className="primary-button"
                        type="button"
                        data-testid="button-view-stash"
                        onClick={() => setModal('stash')}
                      >
                        View Stash <ArrowUpRight size={14} />
                      </button>
                    </div>
                  </div>
                </article>

                {/* Credit Score card */}
                <article className="card credit-card stagger-2" data-testid="card-credit-score">
                  <div className="card-head">
                    <div>
                      <h3 className="card-title">Gig Credit Score</h3>
                      <p className="card-kicker">Responsible credit, understood</p>
                    </div>
                    <CreditCard size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
                  </div>
                  {scoreError ? (
                    <div className="error-state" role="alert" data-testid="state-score-error">
                      <CircleAlert size={22} strokeWidth={1.7} />
                      <p data-testid="text-score-error-detail">{scoreError}</p>
                    </div>
                  ) : score ? (
                    <div className="score-layout">
                      <div
                        className="score-ring"
                        aria-label={`Credit score ${Math.round(score.final_score)} out of 800`}
                      >
                        <div className="score-inside">
                          <div className="score-number" data-testid="text-credit-score">
                            {Math.round(score.final_score)}
                          </div>
                          <div className="score-outof">out of 800</div>
                          <div className="score-good">{score.category}</div>
                        </div>
                      </div>
                      <div className="score-factors">
                        {score.explanation.length ? (
                          score.explanation.map((factor) => (
                            <div className="factor" key={factor.feature}>
                              <Check size={14} className="factor-icon" strokeWidth={2.5} />
                              {FEATURE_LABELS[factor.feature] ?? factor.feature}
                            </div>
                          ))
                        ) : (
                          <div className="factor">
                            <Check size={14} className="factor-icon" strokeWidth={2.5} />
                            Scored on transparent rules
                          </div>
                        )}
                        <button
                          className="info-link"
                          type="button"
                          data-testid="button-score-explanation"
                          onClick={() => setModal('score')}
                        >
                          <Info size={13} /> How this works
                        </button>
                      </div>
                    </div>
                  ) : null}
                </article>
              </div>
            </section>

            {/* ---- Savings activity + resilience progress ---- */}
            <div className="side-stack">
              <article className="card savings-card stagger-3" data-testid="card-savings-activity">
                <div className="card-head">
                  <div>
                    <h2 className="card-title">Savings activity</h2>
                    <p className="card-kicker">Small moves, adding up</p>
                  </div>
                  <HandCoins size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
                </div>
                <div className="savings-body">
                  <div className="savings-amount" data-testid="text-saved-amount">
                    {formatINR(month.total)}
                    <span>
                      saved this month · {month.count} automatic{' '}
                      {month.count === 1 ? 'sweep' : 'sweeps'}
                    </span>
                  </div>
                  <div>
                    <div className="sweep-bars" aria-label="Recent sweep sizes">
                      {sweeps.slice(0, 6).map((sweep) => (
                        <i className="sweep-bar" key={sweep.id} />
                      ))}
                    </div>
                    <div className="sweep-label">
                      30-day income baseline {formatINR(dashboard?.income_30d_baseline ?? 0)}
                    </div>
                  </div>
                </div>
              </article>

              <article className="card progress-card stagger-2" data-testid="card-resilience-progress">
                <div className="progress-top">
                  <div>
                    <h2 className="card-title">Resilience progress</h2>
                    <div className="progress-amount" data-testid="text-resilience-amount">
                      {formatINR(stash)} <span>/ {formatINR(STASH_GOAL)}</span>
                    </div>
                  </div>
                  <div className="percent" data-testid="text-resilience-percent">
                    {Math.round(targetProgress)}%
                  </div>
                </div>
                <div
                  className="large-track"
                  aria-label={`${Math.round(targetProgress)}% resilience progress`}
                >
                  <div className="large-progress" style={{ width: `${targetProgress}%` }} />
                </div>
                <div className="progress-message">
                  <ShieldCheck size={14} />
                  <span>
                    At this pace, you are creating a cushion that can carry you through a slower
                    week.
                  </span>
                </div>
              </article>
            </div>

            {/* ---- Scoring transparency ---- */}
            {score && (
              <article className="card health-card stagger-3" data-testid="card-score-breakdown">
                <div className="card-head" style={{ padding: 0 }}>
                  <div>
                    <h2 className="card-title">How your score was built</h2>
                    <p className="card-kicker">
                      {score.ml_available ? 'Rules blended with the model' : 'Rules only right now'}
                    </p>
                  </div>
                  <Gauge size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
                </div>
                <div className="health-list">
                  <div className="health-factor">
                    <span>Rule engine score</span>
                    <span className="health-value status-good" data-testid="text-rule-score">
                      <i className="status-dot" />
                      {Math.round(score.rule_score)}
                    </span>
                  </div>
                  <div className="health-factor">
                    <span>Model score</span>
                    <span
                      className={`health-value status-${score.ml_available ? 'excellent' : 'good'}`}
                      data-testid="text-ml-score"
                    >
                      <i className="status-dot" />
                      {score.ml_available ? Math.round(score.ml_score ?? 0) : 'Unavailable'}
                    </span>
                  </div>
                  <div className="health-factor">
                    <span>Confidence</span>
                    <span className="health-value status-high" data-testid="text-score-confidence">
                      <i className="status-dot" />
                      {(score.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                <button
                  className="info-link health-link"
                  type="button"
                  data-testid="button-learn-more-health"
                  onClick={() => setModal('score')}
                >
                  Learn more <ChevronRight size={13} />
                </button>
              </article>
            )}

            {/* ---- Recent sweeps ---- */}
            <article className="card sweeps-card stagger-5" data-testid="card-recent-sweeps">
              <div className="card-head">
                <div>
                  <h2 className="card-title">Recent sweeps</h2>
                  <p className="card-kicker">Automatic moves into your Stash</p>
                </div>
                <Clock3 size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
              </div>
              {sweeps.length ? (
                <div className="sweeps-scroll" role="list">
                  {sweeps.map((sweep) => (
                    <SweepRow key={sweep.id} sweep={sweep} />
                  ))}
                </div>
              ) : (
                <div className="empty-state" data-testid="state-empty-sweeps">
                  <HandCoins size={22} />
                  <strong>Your next sweep will show up here</strong>
                  <span>Connect a gig payment and we will help you keep the habit going.</span>
                </div>
              )}
            </article>
          </div>
        )}
      </main>

      {modalContent && <Modal content={modalContent} onClose={() => setModal(null)} />}
    </div>
  );
}

export default function App() {
  return <Home />;
}
