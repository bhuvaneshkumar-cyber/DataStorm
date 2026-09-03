import { useEffect, useState } from 'react';
import { checkLoanEligibility, applyForLoan, fetchMyLoans } from '@/lib/api';
import { HeartPulse, AlertCircle, CheckCircle } from 'lucide-react';

export default function Loans() {
  const [elig, setElig] = useState<any>(null);
  const [myLoans, setMyLoans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [form, setForm] = useState({ amount: '', tenor_months: '12', purpose: '' });

  useEffect(() => {
    Promise.all([checkLoanEligibility(), fetchMyLoans()])
      .then(([e, l]) => {
        setElig(e);
        setMyLoans(l);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    setApplying(true);
    try {
      await applyForLoan({ ...form, amount: parseFloat(form.amount), tenor_months: parseInt(form.tenor_months) });
      alert('Application submitted!');
      const updated = await fetchMyLoans();
      setMyLoans(updated);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setApplying(false);
    }
  };

  if (loading) return <div className="loading">Loading Loan Center...</div>;

  return (
    <div className="loans-page">
      <div className="eligibility-card">
        <div className="card-head">
          <HeartPulse size={24} />
          <h3>Emergency Loan Eligibility</h3>
        </div>
        {elig?.eligible ? (
          <div className="elig-success">
            <p>You are <strong>Eligible</strong> to apply!</p>
            <div className="limits">
              <div>Max Amount: <strong>₹{elig.max_amount_inr?.toLocaleString()}</strong></div>
              <div>Max Tenor: <strong>{elig.max_tenor_months} months</strong></div>
              <div>Indicative Rate: <strong>{elig.indicative_interest_rate_pct}%</strong></div>
            </div>
            <form onSubmit={handleApply} className="loan-form">
              <div className="field">
                <label>Amount (₹)</label>
                <input type="number" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} required />
              </div>
              <div className="field">
                <label>Tenor (Months)</label>
                <input type="number" value={form.tenor_months} onChange={e => setForm({...form, tenor_months: e.target.value})} required />
              </div>
              <div className="field">
                <label>Purpose</label>
                <input type="text" value={form.purpose} onChange={e => setForm({...form, purpose: e.target.value})} />
              </div>
              <button type="submit" disabled={applying} className="primary-button">
                {applying ? 'Applying...' : 'Submit Application'}
              </button>
            </form>
          </div>
        ) : (
          <div className="elig-fail">
            <AlertCircle size={24} />
            <p>{elig?.reason || 'You are not eligible for a loan at this time.'}</p>
          </div>
        )}
      </div>

      <div className="my-loans">
        <h3>My Applications</h3>
        <div className="loan-list">
          {myLoans.map(l => (
            <div key={l.id} className="loan-item">
              <div className="item-info">
                <strong>₹{l.amount}</strong>
                <span>{l.purpose || 'Emergency Loan'}</span>
                <span>{l.tenor_months} months</span>
              </div>
              <div className={`status ${l.status}`}>{l.status}</div>
            </div>
          ))}
          {myLoans.length === 0 && <div className="empty">No applications found.</div>}
        </div>
      </div>
    </div>
  );
}
