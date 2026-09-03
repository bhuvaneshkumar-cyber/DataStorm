/**
 * DataStorm Financial Engine API Client.
 *
 * Base URLs come from Vite env vars with localhost fallbacks for development.
 */

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000';
const ML_URL = import.meta.env.VITE_ML_URL ?? 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Shared Types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  name: string;
  email: string;
  phone?: string;
  role: 'worker' | 'lender';
  language: string;
  employment_type?: string;
}

export interface Transaction {
  id: string;
  timestamp: string;
  amount: number;
  transaction_type: 'debit' | 'platform_payout';
  merchant?: string;
  category?: string;
}

export interface ExpenseSummary {
  total_income: number;
  total_expense: number;
  net: number;
}

export interface Sweep {
  id: string;
  sweep_amount: number;
  reason: string;
  created_at: string;
}

export interface PlatformAccount {
  id: string;
  platform: string;
  account_handle?: string;
  customer_rating?: number;
  weekly_payout?: number;
  gigs_per_week?: number;
  hours_per_week?: number;
  verified: boolean;
}

export interface CreditProfile {
  final_score: number;
  category: string;
  assumptions?: string[];
}

export interface LoanEligibility {
  eligible: boolean;
  max_amount_inr?: number;
  max_tenor_months?: number;
  indicative_interest_rate_pct?: number;
  reason?: string;
}

export interface LoanApplication {
  id: string;
  amount: number;
  tenor_months: number;
  purpose?: string;
  status: 'pending' | 'approved' | 'rejected';
  credit_score?: number;
  risk_grade?: string;
  engine_decision?: string;
  applicant_name?: string;
}

export interface InsuranceRecommendation {
  product_name: string;
  priority: string;
  description: string;
  estimated_premium: number;
  primary_benefit: string;
}

export interface TaxSummary {
  total_tax: number;
  financial_year: string;
  annualised_gross_income: number;
  taxable_income: number;
  monthly_set_aside: number;
  notes?: string[];
  gst_registration_required: boolean;
}

export interface DashboardData {
  total_stash_balance: number;
  income_30d_baseline: number;
  volatility_index?: number;
  recent_sweeps: Sweep[];
}

// ---------------------------------------------------------------------------
// Internal HTTP helper
// ---------------------------------------------------------------------------

async function request<T = unknown>(url: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('auth_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('auth_token');
    window.location.href = '/login';
    // Never resolves after redirect — casting keeps TypeScript happy.
    return new Promise<never>(() => undefined);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `Request failed with status ${res.status}`);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface AuthResponse {
  access_token: string;
  expires_in_hours: number;
  user: User;
}

export async function register(data: {
  name: string;
  email: string;
  password: string;
  phone?: string;
  role: string;
  language: string;
  employment_type?: string;
}): Promise<AuthResponse> {
  const res = await request<AuthResponse>(`${BACKEND_URL}/api/auth/register`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  localStorage.setItem('auth_token', res.access_token);
  return res;
}

export async function login(data: {
  email: string;
  password: string;
  expected_role?: string;
}): Promise<AuthResponse> {
  const res = await request<AuthResponse>(`${BACKEND_URL}/api/auth/login`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  localStorage.setItem('auth_token', res.access_token);
  return res;
}

export async function getProfile(): Promise<User> {
  return request<User>(`${BACKEND_URL}/api/auth/me`);
}

export async function updateProfile(data: Partial<Pick<User, 'name' | 'phone' | 'language'>>): Promise<User> {
  return request<User>(`${BACKEND_URL}/api/auth/me`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// ---------------------------------------------------------------------------
// Transactions & Expenses
// ---------------------------------------------------------------------------

export async function fetchTransactions(): Promise<Transaction[]> {
  return request<Transaction[]>(`${BACKEND_URL}/api/transactions`);
}

export async function createTransaction(data: {
  amount: number;
  transaction_type: string;
  merchant?: string;
  category?: string;
}): Promise<Transaction> {
  return request<Transaction>(`${BACKEND_URL}/api/transactions`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchExpenseSummary(windowDays = 90): Promise<ExpenseSummary> {
  return request<ExpenseSummary>(`${BACKEND_URL}/api/transactions/summary?window_days=${windowDays}`);
}

export async function fetchSweeps(): Promise<Sweep[]> {
  return request<Sweep[]>(`${BACKEND_URL}/api/transactions/sweeps`);
}

export async function authorizeSweep(data: {
  sweep_amount: number;
  reason?: string;
}): Promise<Sweep> {
  return request<Sweep>(`${BACKEND_URL}/api/transactions/sweeps`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ---------------------------------------------------------------------------
// Platforms
// ---------------------------------------------------------------------------

export async function fetchPlatforms(): Promise<PlatformAccount[]> {
  return request<PlatformAccount[]>(`${BACKEND_URL}/api/platforms`);
}

export async function fetchDashboard(): Promise<DashboardData> {
  return request<DashboardData>(`${BACKEND_URL}/api/dashboard`);
}

export async function connectPlatform(data: {
  platform: string;
  account_handle?: string;
  customer_rating?: number;
  weekly_payout?: number;
  gigs_per_week?: number;
  hours_per_week?: number;
}): Promise<PlatformAccount> {
  return request<PlatformAccount>(`${BACKEND_URL}/api/platforms`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function disconnectPlatform(id: string): Promise<void> {
  return request<void>(`${BACKEND_URL}/api/platforms/${id}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Credit
// ---------------------------------------------------------------------------

export async function fetchMyCreditProfile(): Promise<CreditProfile> {
  return request<CreditProfile>(`${BACKEND_URL}/api/credit/score`);
}

export async function analyzeStatement(file: File, overrides: Record<string, unknown> = {}): Promise<{ score: CreditProfile }> {
  const formData = new FormData();
  formData.append('file', file);
  for (const [k, v] of Object.entries(overrides)) {
    if (v !== undefined && v !== null) formData.append(k, String(v));
  }

  const res = await fetch(`${ML_URL}/analyze-statement`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('Statement analysis failed');
  return res.json() as Promise<{ score: CreditProfile }>;
}

// ---------------------------------------------------------------------------
// Loans
// ---------------------------------------------------------------------------

export async function checkLoanEligibility(): Promise<LoanEligibility> {
  return request<LoanEligibility>(`${BACKEND_URL}/api/loans/eligibility`);
}

export async function applyForLoan(data: {
  amount: number;
  tenor_months: number;
  purpose?: string;
}): Promise<LoanApplication> {
  return request<LoanApplication>(`${BACKEND_URL}/api/loans/apply`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchMyLoans(): Promise<LoanApplication[]> {
  return request<LoanApplication[]>(`${BACKEND_URL}/api/loans/my-applications`);
}

export async function fetchPendingLoans(): Promise<LoanApplication[]> {
  return request<LoanApplication[]>(`${BACKEND_URL}/api/loans/review`);
}

export async function decideLoan(appId: string, decision: { status: 'approved' | 'rejected'; lender_note?: string }): Promise<LoanApplication> {
  return request<LoanApplication>(`${BACKEND_URL}/api/loans/${appId}/decision`, {
    method: 'PATCH',
    body: JSON.stringify(decision),
  });
}

// ---------------------------------------------------------------------------
// Insurance
// ---------------------------------------------------------------------------

export async function fetchInsuranceRecs(): Promise<InsuranceRecommendation[]> {
  return request<InsuranceRecommendation[]>(`${BACKEND_URL}/api/insurance/recommend`);
}

// ---------------------------------------------------------------------------
// Tax
// ---------------------------------------------------------------------------

export async function fetchTaxSummary(): Promise<TaxSummary> {
  return request<TaxSummary>(`${BACKEND_URL}/api/tax/summary`);
}

// ---------------------------------------------------------------------------
// Bot
// ---------------------------------------------------------------------------

export interface BotResponse {
  answer: string;
  confident: boolean;
}

export async function askBot(question: string, lang = 'en'): Promise<BotResponse> {
  return request<BotResponse>(`${BACKEND_URL}/api/bot/ask`, {
    method: 'POST',
    body: JSON.stringify({ question, language: lang }),
  });
}

export async function fetchBotTopics(): Promise<{ topics: string[] }> {
  return request<{ topics: string[] }>(`${BACKEND_URL}/api/bot/topics`);
}
