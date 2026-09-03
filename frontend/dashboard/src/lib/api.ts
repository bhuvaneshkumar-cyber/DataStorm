/**
 * Thin fetch wrappers for the two live services. Base URLs come from Vite env
 * vars (set in .env.local, see .env.example) so nothing here breaks when the
 * app is deployed off localhost.
 */

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000';
const ML_URL = import.meta.env.VITE_ML_URL ?? 'http://localhost:8001';
const DEMO_USER_ID = import.meta.env.VITE_DEMO_USER_ID as string | undefined;

export type DashboardStats = {
  user_id: string;
  total_stash_balance: number;
  income_30d_baseline: number;
  recent_sweeps: Array<{
    id: string;
    sweep_amount: number;
    reason: string;
    transaction_id: string | null;
    created_at: string | null;
  }>;
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

export type CreditScoreResponse = {
  final_score: number;
  category: 'Poor' | 'Standard' | 'Good';
  confidence: number;
  ml_available: boolean;
};

export async function fetchDashboard(): Promise<DashboardStats | null> {
  if (!DEMO_USER_ID) return null;
  const res = await fetch(`${BACKEND_URL}/api/users/${DEMO_USER_ID}/dashboard`);
  if (!res.ok) throw new Error(`dashboard fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchCreditScore(payload: CreditScoreRequest): Promise<CreditScoreResponse> {
  const res = await fetch(`${ML_URL}/predict-credit-score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`credit score fetch failed: ${res.status}`);
  return res.json();
}
