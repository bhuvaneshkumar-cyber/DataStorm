/**
 * Financial Engine API Client.
 *
 * Base URLs come from Vite env vars.
 */

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000';
const ML_URL = import.meta.env.VITE_ML_URL ?? 'http://localhost:8001';

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('auth_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem('auth_token');
    window.location.href = '/login';
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

// --- Auth ---
export async function register(data: any) {
  return request(`/auth/register`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function login(data: any) {
  const res = await request<{access_token: string, user: any}>(`${BACKEND_URL}/auth/login`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  localStorage.setItem('auth_token', res.access_token);
  return res;
}

export async function getProfile() {
  return request(`${BACKEND_URL}/auth/profile`);
}

export async function updateProfile(data: any) {
  return request(`${BACKEND_URL}/auth/profile`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// --- Transactions & Expenses ---
export async function fetchTransactions() {
  return request(`${BACKEND_URL}/api/transactions`);
}

export async function createTransaction(data: any) {
  return request(`${BACKEND_URL}/api/transactions`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchExpenseSummary(windowDays = 90) {
  return request(`${BACKEND_URL}/api/transactions/summary?window_days=${windowDays}`);
}

export async function fetchSweeps() {
  return request(`${BACKEND_URL}/api/transactions/sweeps`);
}

export async function authorizeSweep(data: any) {
  return request(`${BACKEND_URL}/api/transactions/sweeps`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Platforms ---
export async function fetchPlatforms() {
  return request(`${BACKEND_URL}/api/platforms`);
}

export async function fetchDashboard() {
  return request(`${BACKEND_URL}/api/dashboard`);
}

export async function connectPlatform(data: any) {
  return request(`${BACKEND_URL}/api/platforms`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function disconnectPlatform(id: string) {
  return request(`${BACKEND_URL}/api/platforms/${id}`, {
    method: 'DELETE',
  });
}

// --- Credit ---
export async function fetchMyCreditProfile() {
  return request(`${BACKEND_URL}/api/credit/score`);
}

export async function analyzeStatement(file: File, overrides: any = {}) {
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
  return res.json();
}

// --- Loans ---
export async function checkLoanEligibility() {
  return request(`${BACKEND_URL}/api/loans/eligibility`);
}

export async function applyForLoan(data: any) {
  return request(`${BACKEND_URL}/api/loans/apply`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchMyLoans() {
  return request(`${BACKEND_URL}/api/loans/my-applications`);
}

export async function fetchPendingLoans() {
  return request(`${BACKEND_URL}/api/loans/review`);
}

export async function decideLoan(appId: string, decision: any) {
  return request(`${BACKEND_URL}/api/loans/${appId}/decision`, {
    method: 'PATCH',
    body: JSON.stringify(decision),
  });
}

// --- Insurance ---
export async function fetchInsuranceRecs() {
  return request(`${BACKEND_URL}/api/insurance/recommend`);
}

// --- Tax ---
export async function fetchTaxSummary() {
  return request(`${BACKEND_URL}/api/tax/summary`);
}

// --- Bot ---
export async function askBot(question: string, lang = 'en') {
  return request(`${BACKEND_URL}/api/bot/ask`, {
    method: 'POST',
    body: JSON.stringify({ question, language: lang }),
  });
}

export async function fetchBotTopics() {
  return request(`${BACKEND_URL}/api/bot/topics`);
}
