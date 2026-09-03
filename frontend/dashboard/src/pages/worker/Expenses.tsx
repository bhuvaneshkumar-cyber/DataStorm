import { useEffect, useState } from 'react';
import { fetchTransactions, fetchExpenseSummary, createTransaction } from '@/lib/api';
import { Plus, TrendingDown, TrendingUp } from 'lucide-react';

export default function Expenses() {
  const [rows, setRows] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ amount: '', transaction_type: 'debit', merchant: '', category: '' });

  useEffect(() => {
    Promise.all([fetchTransactions(), fetchExpenseSummary()])
      .then(([txs, sum]) => {
        setRows(txs);
        setSummary(sum);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createTransaction({ ...form, amount: parseFloat(form.amount) });
      const [txs, sum] = await Promise.all([fetchTransactions(), fetchExpenseSummary()]);
      setRows(txs);
      setSummary(sum);
    } catch (err: any) {
      alert(err.message);
    }
  };

  if (loading) return <div className="loading">Loading Expenses...</div>;

  return (
    <div className="expenses-page">
      <div className="summary-bar">
        <div className="sum-item">
          <span>Total Income</span>
          <strong className="text-green">₹{summary?.total_income?.toLocaleString()}</strong>
        </div>
        <div className="sum-item">
          <span>Total Expense</span>
          <strong className="text-red">₹{summary?.total_expense?.toLocaleString()}</strong>
        </div>
        <div className="sum-item">
          <span>Net Flow</span>
          <strong className={summary?.net >= 0 ? 'text-green' : 'text-red'}>₹{summary?.net?.toLocaleString()}</strong>
        </div>
      </div>

      <div className="expenses-layout">
        <div className="transaction-form">
          <h3>Log Transaction</h3>
          <form onSubmit={handleAdd}>
            <div className="field">
              <label>Amount</label>
              <input type="number" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} required />
            </div>
            <div className="field">
              <label>Type</label>
              <select value={form.transaction_type} onChange={e => setForm({...form, transaction_type: e.target.value})}>
                <option value="debit">Expense</option>
                <option value="platform_payout">Income</option>
              </select>
            </div>
            <div className="field">
              <label>Merchant/Source</label>
              <input type="text" value={form.merchant} onChange={e => setForm({...form, merchant: e.target.value})} />
            </div>
            <div className="field">
              <label>Category</label>
              <input type="text" value={form.category} onChange={e => setForm({...form, category: e.target.value})} />
            </div>
            <button type="submit" className="primary-button">Add Entry</button>
          </form>
        </div>

        <div className="transaction-list">
          <h3>History</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Category</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id}>
                    <td>{r.timestamp ? new Date(r.timestamp).toLocaleDateString() : '-'}</td>
                    <td>{r.merchant || 'Unknown'}</td>
                    <td>{r.category || '-'}</td>
                    <td className={r.transaction_type === 'platform_payout' ? 'text-green' : 'text-red'}>
                      {r.transaction_type === 'platform_payout' ? '+' : '-'}₹{r.amount}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
