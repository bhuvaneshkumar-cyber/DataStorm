/**
 * The API contract, mirrored in TypeScript.
 *
 * Every type here corresponds to a Pydantic model: `backend/schemas.py` for the
 * financial engine, `ml_service/schemas.py` for the scoring service. When one of
 * those changes, this file changes with it -- it is the only place the shapes
 * are written down on the client, so there is exactly one thing to keep in step.
 */

export type Role = 'worker' | 'lender';
export type Language = 'en' | 'hi' | 'ta';
export type TransactionType = 'debit' | 'platform_payout';
export type LoanStatus = 'pending' | 'approved' | 'rejected';
export type GigPlatform = 'Ride-Hailing' | 'Food Delivery' | 'Freelance' | 'Other';

/* ------------------------------------------------------------------ */
/*  Identity                                                          */
/* ------------------------------------------------------------------ */

export type UserProfile = {
  id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  role: Role;
  language: Language;
  employment_type: string | null;
  date_of_birth: string | null;
  created_at: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_in_hours: number;
  user: UserProfile;
};

export type RegisterPayload = {
  name: string;
  email: string;
  password: string;
  phone?: string;
  role?: Role;
  language?: Language;
  employment_type?: string;
  date_of_birth?: string;
};

export type ProfileUpdate = Partial<
  Pick<UserProfile, 'name' | 'phone' | 'language' | 'employment_type' | 'date_of_birth'>
>;

/* ------------------------------------------------------------------ */
/*  Money                                                             */
/* ------------------------------------------------------------------ */

export type SweepDecision = { amount: number; eligible: boolean; reason: string };

export type TransactionCreated = {
  transaction_id: string;
  amount: number;
  transaction_type: TransactionType;
  sweep_decision: SweepDecision;
};

export type Transaction = {
  id: string;
  user_id: string | null;
  amount: number;
  transaction_type: TransactionType;
  merchant: string | null;
  category: string | null;
  status: string | null;
  timestamp: string | null;
};

export type Sweep = {
  id: string;
  sweep_amount: number;
  reason: string | null;
  transaction_id: string | null;
  created_at: string | null;
  user_id?: string | null;
};

export type CashflowPoint = { period: string; income: number; expense: number; net: number };
export type CategoryTotal = { category: string; total: number; share_pct: number };

export type ExpenseSummary = {
  window_days: number;
  total_income: number;
  total_expense: number;
  net: number;
  daily: CashflowPoint[];
  monthly: CashflowPoint[];
  expense_categories: CategoryTotal[];
  income_sources: CategoryTotal[];
  transaction_count: number;
};

export type DashboardStats = {
  user_id: string;
  total_stash_balance: number;
  income_30d_baseline: number;
  pending_contributions: number;
  recent_sweeps: Sweep[];
};

/* ------------------------------------------------------------------ */
/*  Platforms                                                         */
/* ------------------------------------------------------------------ */

export type PlatformAccountInput = {
  platform: string;
  account_handle?: string | null;
  customer_rating?: number | null;
  weekly_payout?: number | null;
  gigs_per_week?: number | null;
  hours_per_week?: number | null;
};

export type PlatformAccount = PlatformAccountInput & {
  id: string;
  verified: boolean;
  connected_at: string | null;
};

/** Connected platforms plus the ledger, collapsed into the eight scored features. */
export type IncomeProfile = {
  primary_gig_platform: GigPlatform;
  platform_customer_rating: number;
  average_weekly_payout: number;
  completed_gigs_per_week: number;
  active_platform_hours_per_week: number;
  payout_volatility_index: number;
  resilience_stash_balance: number;
  age: number;
  connected_platforms: number;
  verified_platforms: number;
  /** Values that fell back to a default, so the UI can ask rather than assume. */
  assumptions: string[];
};

/* ------------------------------------------------------------------ */
/*  Credit                                                            */
/* ------------------------------------------------------------------ */

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

export type ShapFactor = { feature: string; impact: number; direction: 'positive' | 'negative' };

export type CreditScore = {
  final_score: number;
  category: 'Poor' | 'Standard' | 'Good';
  confidence: number;
  rule_score: number;
  ml_score: number | null;
  ml_available: boolean;
  explanation: ShapFactor[];
  risk_assessment: RiskAssessment | null;
  latency_ms: number;
};

export type ScoredProfile = { profile: IncomeProfile; score: CreditScore };

export type MetricDetail = {
  name: string;
  value: number;
  score: number;
  status: string;
  description: string;
};

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
export type StatementScore = {
  statement_analysis: {
    source_format: string;
    extraction_method: string | null;
    derived_features: Record<string, number | string>;
    supplied_features: Record<string, { value: number | string; source: 'caller' | 'default' }>;
    unresolved_features: string[];
    evidence: Record<string, unknown>;
    warnings: string[];
  };
  features_used: Record<string, number | string>;
  score: CreditScore;
  metric_analysis: MetricAnalysis | null;
};

/* ------------------------------------------------------------------ */
/*  Corporate financials                                              */
/* ------------------------------------------------------------------ */

export type MetricSource = 'reported' | 'derived' | 'estimated' | 'unavailable';

/** `value` is null when the figure is unknown. Null is never the same as zero. */
export type FinancialMetric = {
  name: string;
  value: number | null;
  source: MetricSource;
  basis: string;
};

export type FinancialAnalysis = {
  source_format: string | null;
  extraction_method: string | null;
  reporting_scale: string;
  scale_multiplier: number;
  metrics: Record<string, FinancialMetric>;
  ratios: Record<string, FinancialMetric>;
  unresolved: string[];
  evidence: Record<string, unknown>;
  warnings: string[];
};

export type BankRow = {
  type: 'credit' | 'debit';
  amount: number;
  description?: string;
  category?: string;
};

/* ------------------------------------------------------------------ */
/*  Insurance                                                         */
/* ------------------------------------------------------------------ */

export type InsuranceOption = {
  code: string;
  title: string;
  description: string;
  priority: number;
  urgency: 'essential' | 'recommended' | 'optional';
  reasons: string[];
  indicative_monthly_premium_inr: [number, number] | null;
  premium_pct_of_weekly_payout: [number, number];
};

export type InsuranceRecommendation = {
  employment_type: string | null;
  matched_exposure_profile: string;
  risk_tier: RiskAssessment['risk_tier'];
  credit_score: number;
  savings_runway_weeks: number;
  recommendations: InsuranceOption[];
  notes: string[];
};

export type InsuranceResponse = {
  profile: IncomeProfile;
  score: CreditScore;
  recommendation: InsuranceRecommendation;
};

/* ------------------------------------------------------------------ */
/*  Loans                                                             */
/* ------------------------------------------------------------------ */

export type LoanEligibility = {
  eligible: boolean;
  credit_score: number;
  threshold: number;
  reason: string;
  max_amount_inr: number;
  max_tenor_months: number;
  indicative_interest_rate_pct: number | null;
  risk_grade: string | null;
};

export type LoanApplication = {
  id: string;
  user_id: string;
  amount: number;
  tenor_months: number;
  purpose: string | null;
  credit_score: number;
  risk_grade: string | null;
  risk_tier: string | null;
  indicative_interest_rate_pct: number | null;
  max_credit_limit_inr: number | null;
  engine_decision: string | null;
  status: LoanStatus;
  lender_note: string | null;
  created_at: string | null;
  decided_at: string | null;
  /** Present only on the lender's view of an application. */
  applicant_name?: string | null;
  applicant_email?: string | null;
};

/* ------------------------------------------------------------------ */
/*  Tax                                                               */
/* ------------------------------------------------------------------ */

export type TaxSlab = { band: string; rate_pct: number; taxable_in_band: number; tax: number };

export type TaxSummary = {
  financial_year: string;
  regime: string;
  observed_days: number;
  gross_income_observed: number;
  annualised_gross_income: number;
  presumptive_deduction: number;
  deductions_claimed: number;
  taxable_income: number;
  slabs: TaxSlab[];
  tax_before_rebate: number;
  rebate: number;
  surcharge: number;
  cess: number;
  total_tax: number;
  effective_rate_pct: number;
  monthly_set_aside: number;
  gst_registration_required: boolean;
  notes: string[];
};

/* ------------------------------------------------------------------ */
/*  Policy bot & health                                               */
/* ------------------------------------------------------------------ */

export type BotAnswer = {
  answer: string;
  confident: boolean;
  sources: Array<{ topic: string; score: number }>;
  suggestions: string[];
};

export type ScoringHealth = {
  status: string;
  ml_model_loaded: boolean;
  mode: 'hybrid' | 'rules_only';
  ingestion_formats: Record<string, boolean>;
};
