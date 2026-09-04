/** Product + integration configuration. Nothing here stands in for API data. */

/** Buffer the resilience progress bar is measured against, in rupees. */
export const STASH_GOAL = 20000;

/**
 * Gig-platform attributes the scoring model needs.
 *
 * These describe the worker's activity on the gig platform itself (ratings,
 * gigs completed, hours online). A production build reads them from the
 * platform connector; no such endpoint exists in this repo yet, so the demo
 * ships one profile here. The two financial inputs the model also takes —
 * stash balance and weekly payout — are NOT listed: those come from the live
 * dashboard response at call time.
 */
export const WORKER_PLATFORM_PROFILE = {
  age: 29,
  primary_gig_platform: 'Ride-Hailing',
  platform_customer_rating: 4.7,
  completed_gigs_per_week: 62,
  payout_volatility_index: 0.18,
  active_platform_hours_per_week: 44,
} as const;
