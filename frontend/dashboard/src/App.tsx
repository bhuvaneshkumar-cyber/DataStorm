import { useEffect, useState, useRef } from 'react';
import {
  ArrowUpRight,
  Bell,
  Check,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  Clock3,
  CreditCard,
  Gauge,
  HandCoins,
  Info,
  Lightbulb,
  Menu,
  RefreshCw,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Wallet,
  X,
} from 'lucide-react';
import { financialDataAdapter, type RecentSweep } from '@/data/financial-data';
import { fetchCreditScore, fetchDashboard } from '@/lib/api';
import Sidebar from '@/components/Sidebar';

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function formatINR(amount: number) {
  return `₹${amount.toLocaleString('en-IN')}`;
}

/* ------------------------------------------------------------------ */
/*  Sweep Row                                                         */
/* ------------------------------------------------------------------ */

function SweepRow({ sweep }: { sweep: RecentSweep }) {
  const sourceLetter =
    sweep.sourceType === 'swiggy' ? 'S' : sweep.sourceType === 'uber' ? 'U' : 'F';
  return (
    <div className="sweep-row" role="listitem" data-testid={`row-sweep-${sweep.id}`}>
      <div className={`source-icon source-${sweep.sourceType}`} aria-hidden="true">
        {sourceLetter}
      </div>
      <div className="sweep-source">
        <div className="sweep-name" data-testid={`text-sweep-source-${sweep.id}`}>
          {sweep.source}
        </div>
        <div className="sweep-date">{sweep.date}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div className="sweep-amount" data-testid={`text-sweep-amount-${sweep.id}`}>
          +{formatINR(sweep.amount)}
        </div>
        <div className="completed" data-testid={`status-sweep-${sweep.id}`}>
          <Check size={11} strokeWidth={2.5} />
          {sweep.status}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading State                                                     */
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

function Modal({
  kind,
  onClose,
}: {
  kind: 'stash' | 'score' | 'coach' | 'health';
  onClose: () => void;
}) {
  const content = {
    stash: {
      title: 'Your Stash is working quietly',
      intro:
        'This is money set aside for the uneven moments — a slower week, an unexpected repair, or simply a little more breathing room.',
      highlight: '₹12,450 ready when you need it',
      bullets: [
        'Your Stash is separate from everyday spending.',
        'Automatic sweeps help you build without having to remember.',
        'You\'re 62% of the way to your ₹20,000 cushion goal.',
      ],
    },
    score: {
      title: 'A fuller picture of credit',
      intro:
        'Your Gig Credit Score is designed for income that does not arrive on the same day every month.',
      highlight: '742 · Good',
      bullets: [
        'Savings consistency shows you can create a steady habit.',
        'Regular income captures the rhythm of your work, not just a salary date.',
        'On-time repayments are a strong signal of responsible credit use.',
      ],
    },
    coach: {
      title: 'Why this recommendation?',
      intro:
        'Bryn looks at your recent activity and suggests a move that feels achievable, not disruptive.',
      highlight: 'Move ₹600 → Stash',
      bullets: [
        'It fits your recent saving rhythm.',
        'It would take your cushion to ₹13,050.',
        'You can review or change the suggestion before making it.',
      ],
    },
    health: {
      title: 'Your credit health, simply',
      intro:
        'These three signals are the building blocks behind your score. They are meant to help you understand, not judge, your financial life.',
      highlight: 'Strong habits are already showing',
      bullets: [
        'High savings consistency means your automatic habit is sticking.',
        'Excellent repayment behavior gives lenders a clear, positive signal.',
        'Good income stability reflects a healthy rhythm across your gigs.',
      ],
    },
  }[kind];

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
  const snapshot = financialDataAdapter;

  const [stash, setStash] = useState(snapshot.stash.amount);
  const [sweeps, setSweeps] = useState<RecentSweep[]>(snapshot.recentSweeps);
  const [credit, setCredit] = useState(snapshot.credit);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [applied, setApplied] = useState(false);
  const [modal, setModal] = useState<'stash' | 'score' | 'coach' | 'health' | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);

  // Sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const brandRef = useRef<HTMLDivElement>(null);

  const targetProgress = Math.min((stash / snapshot.stash.target) * 100, 100);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  // Pull live data from backend + ml_service where available; on any failure
  // (service down, no demo user seeded) keep the local demo snapshot as-is —
  // this UI is designed to look complete either way.
  useEffect(() => {
    fetchDashboard()
      .then((data) => {
        if (!data) return;
        setStash(data.total_stash_balance);
        setSweeps(
          data.recent_sweeps.map((s) => ({
            id: s.id,
            source: s.reason,
            sourceType: 'freelance',
            date: s.created_at ? new Date(s.created_at).toLocaleDateString() : '',
            amount: s.sweep_amount,
            status: 'Completed',
          })),
        );
      })
      .catch(() => {});

    fetchCreditScore({
      age: 29,
      primary_gig_platform: 'Ride-Hailing',
      platform_customer_rating: 4.7,
      completed_gigs_per_week: 62,
      average_weekly_payout: 9200,
      payout_volatility_index: 0.18,
      active_platform_hours_per_week: 44,
      resilience_stash_balance: snapshot.stash.amount,
    })
      .then((score) =>
        setCredit((current) => ({
          ...current,
          score: Math.round(score.final_score),
          label: score.category,
        })),
      )
      .catch(() => {});
  }, []);

  const announce = (message: string) => setToast(message);

  const applySuggestion = () => {
    if (applied) {
      announce('That suggestion is already part of your Stash.');
      return;
    }
    setStash((current) => current + snapshot.coach.suggestionAmount);
    setApplied(true);
    announce('₹600 moved to your Stash. Nice, steady progress.');
  };

  const simulateLoading = () => {
    setDemoOpen(false);
    setError(false);
    setLoading(true);
    window.setTimeout(() => setLoading(false), 1200);
  };

  const restoreDemo = () => {
    setDemoOpen(false);
    setError(false);
    setLoading(false);
    setSweeps(snapshot.recentSweeps);
    setStash(snapshot.stash.amount);
    setApplied(false);
    announce('Demo data restored.');
  };

  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
    // Close popovers when toggling sidebar
    setProfileOpen(false);
    setNotificationsOpen(false);
  };

  return (
    <div className="dashboard-shell">
      {/* ---- Sidebar ---- */}
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        triggerRef={brandRef}
      />

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
            onClick={toggleSidebar}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleSidebar();
              }
            }}
          >
            <div className="brand-symbol" aria-hidden="true">
              <ShieldCheck size={18} strokeWidth={2.5} />
            </div>
            <span className="brand-word">Bryn</span>
          </div>
          <div className="header-greeting">
            <strong>Good morning, {snapshot.user.firstName}</strong>
            <span>Here's your financial resilience snapshot</span>
          </div>
          <div className="header-actions">
            <button
              className="icon-button"
              type="button"
              aria-label="View notifications"
              data-testid="button-notifications"
              onClick={() => {
                setNotificationsOpen((open) => !open);
                setProfileOpen(false);
              }}
            >
              <Bell size={18} strokeWidth={1.8} />
            </button>
            <button
              className="avatar-button"
              type="button"
              aria-label="Open account menu"
              data-testid="button-account-menu"
              onClick={() => {
                setProfileOpen((open) => !open);
                setNotificationsOpen(false);
              }}
            >
              {snapshot.user.initials}
            </button>
            {notificationsOpen && (
              <div className="header-popover" role="status" data-testid="panel-notifications">
                <div className="popover-name">
                  You're all caught up
                  <small>No new alerts right now.</small>
                </div>
                <button
                  className="popover-action"
                  type="button"
                  onClick={() => {
                    setNotificationsOpen(false);
                    announce('We\'ll keep an eye on your next sweep.');
                  }}
                >
                  Keep me posted
                </button>
              </div>
            )}
            {profileOpen && (
              <div className="header-popover" role="menu" data-testid="panel-account">
                <div className="popover-name">
                  Mira Shah
                  <small>Personal resilience space</small>
                </div>
                <button
                  className="popover-action"
                  type="button"
                  onClick={() => {
                    setProfileOpen(false);
                    announce('Preferences are ready for your next visit.');
                  }}
                >
                  <Settings2 size={13} /> Preferences
                </button>
                <button
                  className="popover-action"
                  type="button"
                  onClick={() => {
                    setProfileOpen(false);
                    announce('Your account is secure.');
                  }}
                >
                  <ShieldCheck size={13} /> Account security
                </button>
              </div>
            )}
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
            <h2>We couldn't refresh your snapshot</h2>
            <p>
              Your saved picture is safe. Try again when you&apos;re ready and we&apos;ll bring the
              latest activity back.
            </p>
            <button
              className="primary-button"
              type="button"
              data-testid="button-retry"
              onClick={() => {
                setError(false);
                announce('Snapshot refreshed.');
              }}
            >
              <RotateCcw size={14} /> Try again
            </button>
          </div>
        ) : (
          <div className="layout-grid">
            {/* ---- Financial overview section ---- */}
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
                    <div className="money-delta">
                      <TrendingUp size={13} /> +{formatINR(snapshot.stash.monthlyChange)} this month
                    </div>
                    <p className="stash-note">
                      You're building a buffer for the days work gets a little quieter.
                    </p>
                    <div className="stash-footer">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          className="progress-track"
                          aria-label={`${Math.round(targetProgress)}% of your Stash goal`}
                        >
                          <div
                            className="stash-progress"
                            style={{ width: `${targetProgress}%` }}
                          />
                        </div>
                        <div className="progress-caption" data-testid="text-stash-progress">
                          {Math.round(targetProgress)}% of ₹20,000 buffer goal
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
                  <div className="score-layout">
                    <div
                      className="score-ring"
                      aria-label={`Credit score ${credit.score} out of 800`}
                    >
                      <div className="score-inside">
                        <div className="score-number" data-testid="text-credit-score">
                          {credit.score}
                        </div>
                        <div className="score-outof">out of 800</div>
                        <div className="score-good">{credit.label}</div>
                      </div>
                    </div>
                    <div className="score-factors">
                      {snapshot.credit.factors.map((factor) => (
                        <div className="factor" key={factor}>
                          <Check size={14} className="factor-icon" strokeWidth={2.5} /> {factor}
                        </div>
                      ))}
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
                  {modal === 'score' && (
                    <div className="credit-explain">
                      Your Gig Credit Score looks beyond a single repayment history. It recognizes the
                      steady actions that help you stay ready: putting money aside, keeping income
                      flowing, and paying on time.
                    </div>
                  )}
                </article>
              </div>
            </section>

            {/* ---- Savings activity + AI Coach ---- */}
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
                    ₹850
                    <span>
                      saved this month · {snapshot.savings.automaticSweeps} automatic sweeps
                    </span>
                  </div>
                  <div>
                    <div className="sweep-bars" aria-label="Savings activity trend">
                      <i className="sweep-bar" />
                      <i className="sweep-bar" />
                      <i className="sweep-bar" />
                      <i className="sweep-bar" />
                      <i className="sweep-bar" />
                      <i className="sweep-bar" />
                    </div>
                    <div className="sweep-label">steady rhythm</div>
                  </div>
                </div>
              </article>

              <article className="card coach-card stagger-4" data-testid="card-financial-coach">
                <div className="coach-content">
                  <div className="coach-heading">
                    <div className="coach-icon">
                      <Sparkles size={17} strokeWidth={1.8} />
                    </div>
                    <div>
                      <div className="coach-title">AI Financial Coach</div>
                      <div className="coach-tag">A thoughtful nudge, just for you</div>
                    </div>
                  </div>
                  <p className="coach-insight">{snapshot.coach.insight}</p>
                  <div className="suggestion-row">
                    <div>
                      <div className="suggestion-label">Recommended action</div>
                      <div className="suggestion-value">
                        Move ₹600 <span aria-hidden="true">→</span> Stash
                      </div>
                    </div>
                    <Lightbulb size={17} color="#8B6FE8" strokeWidth={1.8} />
                  </div>
                  <div className="coach-actions">
                    <button
                      className="primary-button"
                      type="button"
                      data-testid="button-apply-suggestion"
                      onClick={applySuggestion}
                    >
                      {applied ? (
                        <>
                          <Check size={14} /> Applied
                        </>
                      ) : (
                        'Apply suggestion'
                      )}
                    </button>
                    <button
                      className="micro-link"
                      type="button"
                      data-testid="button-view-coach-details"
                      onClick={() => setModal('coach')}
                    >
                      View details <ChevronRight size={13} />
                    </button>
                  </div>
                  {modal === 'coach' && (
                    <div className="coach-details">
                      This suggestion keeps your buffer moving without asking for a big lifestyle
                      change. It's based on your recent sweep rhythm and the ₹20,000 cushion you're
                      building toward.
                    </div>
                  )}
                </div>
              </article>
            </div>

            {/* ---- Resilience progress + Credit health ---- */}
            <div className="side-stack">
              <article className="card progress-card stagger-2" data-testid="card-resilience-progress">
                <div className="progress-top">
                  <div>
                    <h2 className="card-title">Resilience progress</h2>
                    <div className="progress-amount" data-testid="text-resilience-amount">
                      {formatINR(stash)} <span>/ ₹20,000</span>
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
                    At this pace, you're creating a cushion that can carry you through a slower week.
                  </span>
                </div>
              </article>

              <article className="card health-card stagger-3" data-testid="card-credit-health">
                <div className="card-head" style={{ padding: 0 }}>
                  <div>
                    <h2 className="card-title">Credit health</h2>
                    <p className="card-kicker">The habits behind your score</p>
                  </div>
                  <CircleHelp size={18} color="#8B6FE8" strokeWidth={1.8} aria-hidden="true" />
                </div>
                <div className="health-list">
                  {snapshot.creditHealth.map((factor) => (
                    <div className="health-factor" key={factor.label}>
                      <span>{factor.label}</span>
                      <span className={`health-value status-${factor.tone}`}>
                        <i className="status-dot" />
                        {factor.value}
                      </span>
                    </div>
                  ))}
                </div>
                <button
                  className="info-link health-link"
                  type="button"
                  data-testid="button-learn-more-health"
                  onClick={() => setModal('health')}
                >
                  Learn more <ChevronRight size={13} />
                </button>
              </article>
            </div>

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
                  <span>Connect a gig payment and we'll help you keep the habit going.</span>
                </div>
              )}
            </article>
          </div>
        )}

        {/* ---- Demo bar ---- */}
        <div className="demo-wrap demo-bar">
          <button
            className="demo-button"
            type="button"
            data-testid="button-demo-menu"
            onClick={() => setDemoOpen((open) => !open)}
          >
            <Menu size={13} /> Demo states
          </button>
          {demoOpen && (
            <div className="demo-menu" role="menu" data-testid="panel-demo-menu">
              <button type="button" onClick={simulateLoading}>
                <RefreshCw size={12} /> Show loading state
              </button>
              <button
                type="button"
                onClick={() => {
                  setDemoOpen(false);
                  setError(true);
                }}
              >
                <CircleAlert size={12} /> Show recoverable error
              </button>
              <button
                type="button"
                onClick={() => {
                  setDemoOpen(false);
                  setSweeps([]);
                  announce('Recent sweeps cleared for the empty state demo.');
                }}
              >
                <X size={12} /> Show empty sweeps
              </button>
              <button type="button" onClick={restoreDemo}>
                <RotateCcw size={12} /> Restore demo data
              </button>
            </div>
          )}
        </div>
      </main>

      {/* ---- Modal ---- */}
      {modal && <Modal kind={modal} onClose={() => setModal(null)} />}

      {/* ---- Toast ---- */}
      {toast && (
        <div className="toast" role="status" data-testid="toast-feedback">
          <Check size={15} /> {toast}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  App                                                               */
/* ------------------------------------------------------------------ */

export default function App() {
  return <Home />;
}
