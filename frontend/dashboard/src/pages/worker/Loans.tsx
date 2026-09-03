import { useEffect, useState } from 'react';
import { checkLoanEligibility, applyForLoan, fetchMyLoans, LoanEligibility, LoanApplication } from '@/lib/api';
import { HeartPulse, AlertCircle, CheckCircle2 } from 'lucide-react';

interface LoanForm {
  amount: string;
  tenor_months: string;
  purpose: string;
}

const EMPTY_FORM: LoanForm = { amount: '', tenor_months: '12', purpose: '' };

export default function Loans() {
  const [elig, setElig] = useState<LoanEligibility | null>(null);
  const [myLoans, setMyLoans] = useState<LoanApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState('');
  const [applySuccess, setApplySuccess] = useState('');
  const [form, setForm] = useState<LoanForm>(EMPTY_FORM);

  useEffect(() => {
    Promise.all([checkLoanEligibility(), fetchMyLoans()])
      .then(([e, l]) => {
        setElig(e);
        setMyLoans(l);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    setApplying(true);
    setApplyError('');
    setApplySuccess('');
    try {
      await applyForLoan({
        amount: parseFloat(form.amount),
        tenor_months: parseInt(form.tenor_months, 10),
        purpose: form.purpose,
      });
      setApplySuccess('Application submitted successfully!');
      setForm(EMPTY_FORM);
      const updated = await fetchMyLoans();
      setMyLoans(updated);
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : 'Failed to submit application.');
    } finally {
      setApplying(false);
    }
  };

  if (loading) return <div className="loading">Calculating loan eligibility...</div>;

  return (
    <div className="loans-page">
      <div className="eligibility-card">
        <div className="card-head">
          <HeartPulse size={24} color="var(--primary)" />
          <h3>Emergency Loan Access</h3>
        </div>

        {elig?.eligible ? (
          <div className="elig-success">
            <div className="elig-badge">
              <CheckCircle2 size={20} /> You are Eligible to Apply
            </div>
            <div className="limits">
              <div>
                <span>Max Amount</span>
                <strong>₹{elig.max_amount_inr?.toLocaleString()}</strong>
              </div>
              <div>
                <span>Max Tenor</span>
                <strong>{elig.max_tenor_months} months</strong>
              </div>
              <div>
                <span>Indicative Rate</span>
                <strong>{elig.indicative_interest_rate_pct}%</strong>
              </div>
            </div>

            {applyError && <div className="error-msg">{applyError}</div>}
            {applySuccess && <div className="success-msg">{applySuccess}</div>}

            <form onSubmit={handleApply} className="loan-form">
              <div className="field">
                <label>Desired Amount (₹)</label>
                <input
                  type="number"
                  value={form.amount}
                  onChange={e => setForm({ ...form, amount: e.target.value })}
                  required
                />
              </div>
              <div className="field">
                <label>Tenor (Months)</label>
                <input
                  type="number"
                  value={form.tenor_months}
                  onChange={e => setForm({ ...form, tenor_months: e.target.value })}
                  required
                />
              </div>
              <div className="field">
                <label>Purpose of Loan</label>
                <input
                  type="text"
                  value={form.purpose}
                  onChange={e => setForm({ ...form, purpose: e.target.value })}
                  placeholder="e.g. Medical Emergency"
                />
              </div>
              <button type="submit" disabled={applying} className="primary-button">
                {applying ? 'Processing...' : 'Submit Application'}
              </button>
            </form>
          </div>
        ) : (
          <div className="elig-fail">
            <AlertCircle size={32} color="var(--warning)" />
            <div className="elig-fail-title">Eligibility Not Met</div>
            <p>{elig?.reason ?? 'You are not eligible for a loan at this time based on your current resilience buffer.'}</p>
          </div>
        )}
      </div>

      <div className="my-loans">
        <div className="card-title">My Applications</div>
        <div className="loan-list">
          {myLoans.map(l => (
            <div key={l.id} className="loan-item">
              <div className="item-info">
                <strong>₹{l.amount?.toLocaleString()}</strong>
                <span>{l.purpose ?? 'Emergency Loan'}</span>
                <span>{l.tenor_months} months</span>
              </div>
              <div className={`status ${l.status}`}>{l.status}</div>
            </div>
          ))}
          {myLoans.length === 0 && <div className="empty-state">No active loan applications.</div>}
        </div>
      </div>
    </div>
  );
}
