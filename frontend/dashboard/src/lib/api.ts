/**
 * Thin fetch wrappers for the two live services. Base URLs come from Vite env
 * vars (set in .env.local, see .env.example) so nothing here breaks when the
 * app is deployed off localhost.
 *
 * Every call surfaces a readable message on failure rather than a bare status
 * code: the UI shows these directly, and "credit score fetch failed: 422" tells
 * a user nothing about which field was wrong.
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

/** Underwriting view returned alongside every score. */
export type RiskAssessment = {
  risk_grade: { code: string; label: string };
  risk_tier: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH';
  decision: 'APPROVE' | 'REFER' | 'DECLINE';
  indicative_interest_rate_pct: number;
  risk_premium_bps: number;
  max_credit_limit_inr: number;
  recommended_tenor_months: number;
  conditions: string[];
  early_warning_signals: Array<{ code: string; title: string; detail: string }>;
};

export type CreditScoreResponse = {
  final_score: number;
  category: 'Poor' | 'Standard' | 'Good';
  confidence: number;
  rule_score: number;
  ml_score: number | null;
  ml_available: boolean;
  /** Null only if the service is running a build older than v1.1.0. */
  risk_assessment: RiskAssessment | null;
  latency_ms: number;
};

/** One standardized ledger row, as ml_service/credit_metrics.py consumes them. */
export type LedgerTransaction = {
  date: string;
  type: 'credit' | 'debit';
  amount: number;
  category?: string | null;
  source?: string | null;
  description?: string | null;
};

export type MetricDetail = {
  name: string;
  value: number;
  score: number;
  status: string;
  description: string;
};

/** Transaction-driven breakdown: the "why" behind a score, metric by metric. */
export type MetricAnalysis = {
  credit_score: number;
  composite_score: number;
  category_scores: Record<string, number>;
  category_weights: Record<string, number>;
  metrics: Record<string, MetricDetail>;
  strengths: string[];
  weaknesses: string[];
  recommended_actions: string[];
  coverage: {
    transactions: number;
    credits: number;
    debits: number;
    months_observed: number;
    period_start: string;
    period_end: string;
  };
  risk_grade: { code: string; label: string };
};

/** Provenance for a scored statement: what was read, and what was assumed. */
export type StatementScoreResponse = {
  statement_analysis: {
    source_format: string;
    extraction_method: string | null;
    derived_features: Record<string, number | string>;
    supplied_features: Record<string, { value: number | string; source: 'caller' | 'default' }>;
    unresolved_features: string[];
    evidence: Record<string, unknown>;
    warnings: string[];
  };
  features_used: CreditScoreRequest;
  score: CreditScoreResponse;
  metric_analysis: MetricAnalysis | null;
};

export type ServiceHealth = {
  status: string;
  ml_model_loaded: boolean;
  mode: 'hybrid' | 'rules_only';
  ingestion_formats: Record<string, boolean>;
};

/**
 * Turns a failed response into an Error carrying the server's own explanation.
 *
 * FastAPI puts the reason in `detail`, either as a string or as a list of
 * per-field validation errors. Both are unwrapped here so no caller has to.
 */
async function toError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return new Error(detail);
    if (Array.isArray(detail) && detail.length) {
      return new Error(
        detail
          .map((item: { loc?: unknown[]; msg?: string }) => {
            const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : '';
            return field ? `${field}: ${item.msg}` : item.msg;
          })
          .join('; '),
      );
    }
  } catch {
    // Body was not JSON (a proxy error page, an empty 502). Fall through.
  }
  return new Error(`${fallback} (HTTP ${res.status})`);
}

async function getJson<T>(url: string, fallback: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw await toError(res, fallback);
  return res.json();
}

export async function fetchServiceHealth(): Promise<ServiceHealth> {
  return getJson<ServiceHealth>(`${ML_URL}/health`, 'Scoring service is unreachable');
}

/** Null when no demo user is configured — not an error, just nothing to show. */
export async function fetchDashboard(): Promise<DashboardStats | null> {
  if (!DEMO_USER_ID) return null;
  return getJson<DashboardStats>(
    `${BACKEND_URL}/api/users/${DEMO_USER_ID}/dashboard`,
    'Could not load your dashboard',
  );
}

export async function fetchCreditScore(payload: CreditScoreRequest): Promise<CreditScoreResponse> {
  const res = await fetch(`${ML_URL}/predict-credit-score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await toError(res, 'Could not calculate your credit score');
  return res.json();
}

/**
 * Uploads a bank or platform payout statement and scores whatever it evidences.
 *
 * `overrides` supplies the facts no statement contains (age, rating, hours).
 * Content-Type is deliberately unset: the browser must add the multipart
 * boundary itself, and setting it by hand produces a request the server cannot
 * parse.
 */
export async function analyzeStatement(
  file: File,
  overrides: Partial<
    Pick<
      CreditScoreRequest,
      'age' | 'platform_customer_rating' | 'active_platform_hours_per_week' | 'primary_gig_platform'
    >
  > = {},
): Promise<StatementScoreResponse> {
  const form = new FormData();
  form.append('file', file);
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined && value !== null) form.append(key, String(value));
  }

  const res = await fetch(`${ML_URL}/analyze-statement`, { method: 'POST', body: form });
  if (!res.ok) throw await toError(res, 'Could not read that statement');
  return res.json();
}

/** Scores a ledger directly, for data that never went through a document. */
export async function analyzeTransactions(
  transactions: LedgerTransaction[],
  options: { platform_rating?: number; opening_balance?: number } = {},
): Promise<MetricAnalysis> {
  const res = await fetch(`${ML_URL}/analyze-transactions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transactions, ...options }),
  });
  if (!res.ok) throw await toError(res, 'Could not analyse those transactions');
  return res.json();
}
