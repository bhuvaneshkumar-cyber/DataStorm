import { useEffect, useState } from 'react';
import { fetchTransactions, fetchExpenseSummary, createTransaction, Transaction, ExpenseSummary } from '@/lib/api';
import { Plus, Receipt, PieChart as PieIcon } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

interface TransactionForm {
  amount: string;
  transaction_type: string;
  merchant: string;
  category: string;
}

const EMPTY_FORM: TransactionForm = {
  amount: '',
  transaction_type: 'debit',
  merchant: '',
  category: '',
};

export default function Expenses() {
  const [rows, setRows] = useState<Transaction[]>([]);
  const [summary, setSummary] = useState<ExpenseSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState<TransactionForm>(EMPTY_FORM);

  const loadData = async () => {
    const [txs, sum] = await Promise.all([fetchTransactions(), fetchExpenseSummary()]);
    setRows(txs);
    setSummary(sum);
  };

  useEffect(() => {
    loadData().finally(() => setLoading(false));
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await createTransaction({
        amount: parseFloat(form.amount),
        transaction_type: form.transaction_type,
        merchant: form.merchant,
        category: form.category,
      });
      setForm(EMPTY_FORM);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add transaction.');
    } finally {
      setSubmitting(false);
    }
  };

  const categoryData = rows
    .filter(r => r.transaction_type === 'debit')
    .reduce<{ name: string; value: number }[]>((acc, curr) => {
      const existing = acc.find(item => item.name === curr.category);
      if (existing) {
        existing.value += curr.amount;
      } else {
        acc.push({ name: curr.category ?? 'Other', value: curr.amount });
      }
      return acc;
    }, []);

  if (loading) return <div className="loading">Analyzing cash flow...</div>;

  return (
    <div className="expenses-page">
      <div className="summary-bar">
        <div className="sum-item">
          <span>Total Income</span>
          <strong className="text-green">₹{summary?.total_income?.toLocaleString()}</strong>
        </div>
        <div className="sum-item">
          <span>Total Expenses</span>
          <strong className="text-red">₹{summary?.total_expense?.toLocaleString()}</strong>
        </div>
        <div className="sum-item">
          <span>Net Cash Flow</span>
          <strong className={(summary?.net ?? 0) >= 0 ? 'text-green' : 'text-red'}>
            ₹{summary?.net?.toLocaleString()}
          </strong>
        </div>
      </div>

      <div className="expenses-layout">
        <div className="main-col">
          <div className="card">
            <div className="card-title"><Receipt size={18} /> Transaction History</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Description</th>
                    <th>Category</th>
                    <th style={{ textAlign: 'right' }}>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.id}>
                      <td>{r.timestamp ? new Date(r.timestamp).toLocaleDateString() : '-'}</td>
                      <td><strong>{r.merchant ?? 'Unknown'}</strong></td>
                      <td><span className="category-tag">{r.category ?? 'General'}</span></td>
                      <td
                        style={{ textAlign: 'right', fontWeight: 700 }}
                        className={r.transaction_type === 'platform_payout' ? 'text-green' : 'text-red'}
                      >
                        {r.transaction_type === 'platform_payout' ? '+' : '-'}₹{r.amount?.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length === 0 && <div className="empty-state">No transactions found. Log your first entry!</div>}
            </div>
          </div>
        </div>

        <div className="side-col">
          <div className="card">
            <div className="card-title"><Plus size={18} /> Quick Log</div>
            {error && <div className="error-msg">{error}</div>}
            <form onSubmit={handleAdd} className="transaction-form">
              <div className="field">
                <label>Amount (₹)</label>
                <input
                  type="number"
                  value={form.amount}
                  onChange={e => setForm({ ...form, amount: e.target.value })}
                  required
                />
              </div>
              <div className="field">
                <label>Type</label>
                <select value={form.transaction_type} onChange={e => setForm({ ...form, transaction_type: e.target.value })}>
                  <option value="debit">Expense</option>
                  <option value="platform_payout">Income</option>
                </select>
              </div>
              <div className="field">
                <label>Merchant / Source</label>
                <input
                  type="text"
                  value={form.merchant}
                  onChange={e => setForm({ ...form, merchant: e.target.value })}
                  required
                />
              </div>
              <div className="field">
                <label>Category</label>
                <input
                  type="text"
                  value={form.category}
                  onChange={e => setForm({ ...form, category: e.target.value })}
                  placeholder="e.g. Fuel, Food"
                />
              </div>
              <button type="submit" className="primary-button" disabled={submitting}>
                {submitting ? 'Adding...' : 'Add Transaction'}
              </button>
            </form>
          </div>

          <div className="card spending-chart-card">
            <div className="card-title"><PieIcon size={18} /> Spending Distribution</div>
            <div style={{ width: '100%', height: 250 }}>
              {categoryData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={categoryData}
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {categoryData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend verticalAlign="bottom" height={36} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state">Not enough data for chart.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
