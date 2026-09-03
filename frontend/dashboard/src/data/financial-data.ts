export type SweepStatus = 'Completed' | 'Processing';

export type RecentSweep = {
  id: string;
  source: string;
  sourceType: 'swiggy' | 'uber' | 'freelance';
  date: string;
  amount: number;
  status: SweepStatus;
};

export type FinancialSnapshot = {
  user: {
    firstName: string;
    initials: string;
  };
  stash: {
    amount: number;
    monthlyChange: number;
    target: number;
  };
  credit: {
    score: number;
    label: string;
    factors: string[];
  };
  savings: {
    amount: number;
    automaticSweeps: number;
  };
  coach: {
    insight: string;
    suggestionAmount: number;
  };
  recentSweeps: RecentSweep[];
  creditHealth: Array<{
    label: string;
    value: string;
    tone: 'high' | 'excellent' | 'good';
  }>;
};

/**
 * Presentation-ready local adapter.
 *
 * Replace this object with an API-backed implementation later.
 * Dashboard components consume only the FinancialSnapshot shape,
 * so swapping the data source requires no UI changes.
 *
 * Future API endpoints that will feed this adapter:
 *   GET /api/stash          → stash.amount, stash.monthlyChange, stash.target
 *   GET /api/credit-score   → credit.score, credit.label, credit.factors
 *   GET /api/savings        → savings.amount, savings.automaticSweeps
 *   GET /api/coach          → coach.insight, coach.suggestionAmount
 *   GET /api/sweeps         → recentSweeps[]
 *   GET /api/credit-health  → creditHealth[]
 */
export const financialDataAdapter: FinancialSnapshot = {
  user: { firstName: 'Mira', initials: 'MS' },
  stash: { amount: 12450, monthlyChange: 850, target: 20000 },
  credit: {
    score: 742,
    label: 'Good',
    factors: ['Consistent savings', 'Regular income', 'On-time repayments'],
  },
  savings: { amount: 850, automaticSweeps: 8 },
  coach: {
    insight:
      'Your cushion is growing steadily. One small sweep this week keeps your buffer on track.',
    suggestionAmount: 600,
  },
  recentSweeps: [
    { id: 'swiggy-1', source: 'Swiggy', sourceType: 'swiggy', date: 'Today', amount: 250, status: 'Completed' },
    { id: 'uber-1', source: 'Uber', sourceType: 'uber', date: 'Yesterday', amount: 180, status: 'Completed' },
    { id: 'freelance-1', source: 'Freelance payment', sourceType: 'freelance', date: 'Aug 30', amount: 500, status: 'Completed' },
  ],
  creditHealth: [
    { label: 'Savings consistency', value: 'High', tone: 'high' },
    { label: 'Repayment behavior', value: 'Excellent', tone: 'excellent' },
    { label: 'Income stability', value: 'Good', tone: 'good' },
  ],
};
