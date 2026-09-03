/**
 * Thin fetch wrappers for the two live services.
 *
 * There are deliberately no local fallbacks here. Base URLs must be supplied
 * through Vite env vars and every failure propagates to the caller, so a
 * misconfigured or unreachable backend shows up immediately as an error state
 * instead of quietly rendering plausible-looking numbers that came from nowhere.
 */

function requiredEnv(name: string): string {
  const value = import.meta.env[name as keyof ImportMetaEnv] as string | undefined;
  if (!value) {
    throw new Error(
      `${name} is not set. Copy .env.example to .env.local and point it at your running services.`,
    );
  }
  return value.replace(/\/$/, '');
}

export type RecentSweep = {
  id: string;
  sweep_amount: number;
  reason: string;
  transaction_id: string | null;
  created_at: string | null;
};

export type DashboardStats = {
  user_id: string;
  total_stash_balance: number;
  income_30d_baseline: number;
  pending_contributions: number;
  recent_sweeps: RecentSweep[];
};

/** Matches ml_service/schemas.py CreditScoreRequest exactly (8 gig-worker features). */
export type CreditScoreRequest = {
  age: number;
  primary_gig_platform: 'Ride-Hailing' | 'Food Delivery' | 'Freelance' | 'Other';
  platform_customer_rating: number;
  completed_gigs_per_week: number;
  average_weekly_payout: number;
  payout_volatility_index: number;
  active_platform_hours_per_week: number;
  resilience_stash_balance: number;
};

/** One SHAP factor behind a score — what the model actually keyed on. */
export type ScoreFactor = {
  feature: string;
  impact: number;
  direction: 'positive' | 'negative';
};

export type CreditScoreResponse = {
  final_score: number;
  category: 'Poor' | 'Standard' | 'Good';
  confidence: number;
  rule_score: number;
  ml_score: number | null;
  ml_available: boolean;
  explanation: ScoreFactor[];
  latency_ms: number;
};

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    throw new Error(`Could not reach ${url} (${detail}). Is the service running?`);
  }
  if (!res.ok) {
    throw new Error(`${url} responded ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

/** Live savings figures for the dashboard user, straight from Supabase. */
export function fetchDashboard(): Promise<DashboardStats> {
  const backend = requiredEnv('VITE_FINANCIAL_API_URL');
  const userId = requiredEnv('VITE_DASHBOARD_USER_ID');
  return getJson<DashboardStats>(`${backend}/api/users/${userId}/dashboard`);
}

/** Hybrid rule + RandomForest credit score, with its SHAP explanation. */
export function fetchCreditScore(payload: CreditScoreRequest): Promise<CreditScoreResponse> {
  const ml = requiredEnv('VITE_ML_API_URL');
  return getJson<CreditScoreResponse>(`${ml}/predict-credit-score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
