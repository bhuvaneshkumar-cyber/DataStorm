/**
 * Every endpoint this app calls, one function each, grouped by area.
 *
 * Nothing here does anything but name a route and its types: the transport,
 * the token and the error handling all live in `client.ts`. That split is what
 * keeps this file readable as the API surface, and it means a change to how
 * requests are made touches one file rather than forty call sites.
 */

import { backend, scoring } from './client';
import type {
  AuthResponse,
  BankRow,
  BotAnswer,
  DashboardStats,
  ExpenseSummary,
  FinancialAnalysis,
  IncomeProfile,
  InsuranceResponse,
  LoanApplication,
  LoanEligibility,
  LoanStatus,
  MetricAnalysis,
  PlatformAccount,
  PlatformAccountInput,
  ProfileUpdate,
  RegisterPayload,
  Role,
  ScoredProfile,
  ScoringHealth,
  StatementScore,
  Sweep,
  TaxSummary,
  Transaction,
  TransactionCreated,
  TransactionType,
  UserProfile,
} from './types';

/* ------------------------------------------------------------------ */
/*  Authentication                                                    */
/* ------------------------------------------------------------------ */

export const auth = {
  register: (payload: RegisterPayload) =>
    backend<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: payload,
      auth: false,
      fallback: 'Could not create your account',
    }),

  /**
   * `expectedRole` pins a sign-in to one side of the product, so a worker who
   * lands on the lender portal is told plainly rather than being signed in to
   * a dashboard with nothing on it.
   */
  login: (email: string, password: string, expectedRole?: Role) =>
    backend<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: { email, password, expected_role: expectedRole },
      auth: false,
      fallback: 'Could not sign you in',
    }),

  me: () => backend<UserProfile>('/api/auth/me', { fallback: 'Could not load your profile' }),

  updateProfile: (changes: ProfileUpdate) =>
    backend<UserProfile>('/api/auth/me', {
      method: 'PATCH',
      body: changes,
      fallback: 'Could not save your profile',
    }),
};

/* ------------------------------------------------------------------ */
/*  Money                                                             */
/* ------------------------------------------------------------------ */

export const money = {
  dashboard: () => backend<DashboardStats>('/api/dashboard', { fallback: 'Could not load your dashboard' }),

  transactions: (limit = 50) =>
    backend<Transaction[]>(`/api/transactions?limit=${limit}`, {
      fallback: 'Could not load your transactions',
    }),

  logTransaction: (payload: {
    amount: number;
    transaction_type: TransactionType;
    merchant?: string;
    category?: string;
  }) =>
    backend<TransactionCreated>('/api/transactions', {
      method: 'POST',
      body: payload,
      fallback: 'Could not save that entry',
    }),

  // Backend route: GET /api/expenses/summary?window_days=N
  expenseSummary: (windowDays = 90) =>
    backend<ExpenseSummary>(`/api/expenses/summary?window_days=${windowDays}`, {
      fallback: 'Could not load your cash flow',
    }),

  // Sweeps sit at /api/sweeps, not under /api/transactions
  listSweeps: (limit = 50) =>
    backend<Sweep[]>(`/api/sweeps?limit=${limit}`, {
      fallback: 'Could not load your stash sweeps',
    }),

  authorizeSweep: (sweepAmount: number, reason?: string) =>
    backend<Sweep>('/api/sweeps', {
      method: 'POST',
      body: { sweep_amount: sweepAmount, reason },
      fallback: 'Could not authorize that sweep',
    }),
};

/* ------------------------------------------------------------------ */
/*  Platforms                                                         */
/* ------------------------------------------------------------------ */

export const platforms = {
  list: () => backend<PlatformAccount[]>('/api/platforms', { fallback: 'Could not load your platforms' }),

  connect: (payload: PlatformAccountInput) =>
    backend<PlatformAccount>('/api/platforms', {
      method: 'POST',
      body: payload,
      fallback: 'Could not connect that platform',
    }),

  disconnect: (id: string) =>
    backend<void>(`/api/platforms/${id}`, {
      method: 'DELETE',
      fallback: 'Could not disconnect that platform',
    }),

  incomeProfile: () =>
    backend<IncomeProfile>('/api/platforms/income-profile', {
      fallback: 'Could not build your income profile',
    }),
};

/* ------------------------------------------------------------------ */
/*  Credit                                                            */
/* ------------------------------------------------------------------ */

export const credit = {
  /** Derived server-side from connected platforms and the logged ledger. */
  score: () => backend<ScoredProfile>('/api/credit/score', { fallback: 'Could not calculate your score' }),

  /** Per-metric breakdown of the transactions already logged in the app. */
  metrics: () =>
    backend<MetricAnalysis>('/api/credit/metrics', {
      fallback: 'Could not analyse your transactions',
    }),

  /**
   * Uploads a statement straight to the scoring service rather than through the
   * backend: the document never needs to exist in two places, and the scoring
   * service deletes it before it answers.
   */
  analyzeStatement: (
    file: File,
    overrides: Partial<{
      age: number;
      platform_customer_rating: number;
      active_platform_hours_per_week: number;
      primary_gig_platform: string;
    }> = {},
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append('file', file);
    for (const [key, value] of Object.entries(overrides)) {
      if (value !== undefined && value !== null && value !== '') form.append(key, String(value));
    }
    return scoring<StatementScore>('/analyze-statement', {
      method: 'POST',
      form,
      auth: false,
      fallback: 'Could not read that statement',
      signal,
    });
  },
};

/* ------------------------------------------------------------------ */
/*  Corporate financials                                              */
/* ------------------------------------------------------------------ */

export const financials = {
  analyzeDocument: (file: File, signal?: AbortSignal) => {
    const form = new FormData();
    form.append('file', file);
    return scoring<FinancialAnalysis>('/analyze-financials', {
      method: 'POST',
      form,
      auth: false,
      fallback: 'Could not read those accounts',
      signal,
    });
  },

  estimate: (payload: {
    gst_taxable_turnover?: number | null;
    bank_rows: BankRow[];
    period_months: number;
  }) =>
    scoring<FinancialAnalysis>('/estimate-financials', {
      method: 'POST',
      body: payload,
      auth: false,
      fallback: 'Could not build an estimate',
    }),
};

/* ------------------------------------------------------------------ */
/*  Insurance, loans, tax, bot                                        */
/* ------------------------------------------------------------------ */

export const insurance = {
  // Backend route: GET /api/insurance/recommendations
  recommendations: () =>
    backend<InsuranceResponse>('/api/insurance/recommendations', {
      fallback: 'Could not build an insurance recommendation',
    }),
};

export const loans = {
  eligibility: () =>
    backend<LoanEligibility>('/api/loans/eligibility', {
      fallback: 'Could not check your eligibility',
    }),

  // GET /api/loans — worker's own applications
  mine: () => backend<LoanApplication[]>('/api/loans', { fallback: 'Could not load your applications' }),

  // POST /api/loans — submit a new application
  apply: (payload: { amount: number; tenor_months: number; purpose?: string }) =>
    backend<LoanApplication>('/api/loans', {
      method: 'POST',
      body: payload,
      fallback: 'Could not submit your application',
    }),

  // GET /api/loans/queue — lender review queue
  queue: (status?: LoanStatus) =>
    backend<LoanApplication[]>(`/api/loans/queue${status ? `?status=${status}` : ''}`, {
      fallback: 'Could not load the application queue',
    }),

  // PATCH /api/loans/{id} — lender decision
  decide: (id: string, status: 'approved' | 'rejected', lenderNote?: string) =>
    backend<LoanApplication>(`/api/loans/${id}`, {
      method: 'PATCH',
      body: { status, lender_note: lenderNote },
      fallback: 'Could not record that decision',
    }),
};

export const tax = {
  summary: (options: { deductions?: number; presumptive?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (options.deductions !== undefined) params.set('deductions', String(options.deductions));
    if (options.presumptive !== undefined) params.set('presumptive', String(options.presumptive));
    const query = params.toString();
    return backend<TaxSummary>(`/api/tax/summary${query ? `?${query}` : ''}`, {
      fallback: 'Could not estimate your tax',
    });
  },
};

export const bot = {
  // Returns string[] directly from backend — no wrapping object
  topics: () => backend<string[]>('/api/policy-bot/topics', { fallback: 'Could not load bot topics' }),

  ask: (question: string, language: string) =>
    backend<BotAnswer>('/api/policy-bot/ask', {
      method: 'POST',
      body: { question, language },
      fallback: 'Could not answer that',
    }),
};

export const health = {
  scoring: () => scoring<ScoringHealth>('/health', { auth: false, fallback: 'Scoring service is unreachable' }),
};
