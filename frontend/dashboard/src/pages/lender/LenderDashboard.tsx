import { useEffect, useState } from 'react';
import { fetchPendingLoans, decideLoan, LoanApplication } from '@/lib/api';
import { CheckCircle, XCircle } from 'lucide-react';

export default function LenderDashboard() {
  const [apps, setApps] = useState<LoanApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deciding, setDeciding] = useState<string | null>(null);

  useEffect(() => {
    fetchPendingLoans()
      .then(setApps)
      .catch(() => setError('Failed to load applications.'))
      .finally(() => setLoading(false));
  }, []);

  const handleDecision = async (appId: string, status: 'approved' | 'rejected', note: string) => {
    setDeciding(appId);
    setError('');
    try {
      await decideLoan(appId, { status, lender_note: note });
      const updated = await fetchPendingLoans();
      setApps(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update decision.');
    } finally {
      setDeciding(null);
    }
  };

  if (loading) return <div className="loading">Loading Applications...</div>;

  return (
    <div className="lender-page">
      <h2>Incoming Loan Applications</h2>
      {error && <div className="error-msg">{error}</div>}
      <div className="apps-grid">
        {apps.map(app => (
          <div key={app.id} className="app-card">
            <div className="app-head">
              <strong>{app.applicant_name}</strong>
              <span className="app-score">{app.credit_score}</span>
            </div>
            <div className="app-body">
              <div className="app-row"><span>Amount:</span> <strong>₹{app.amount}</strong></div>
              <div className="app-row"><span>Tenor:</span> <strong>{app.tenor_months} mo</strong></div>
              <div className="app-row"><span>Grade:</span> <strong>{app.risk_grade}</strong></div>
              <div className="app-row">
                <span>Decision:</span>
                <strong className={app.engine_decision === 'APPROVE' ? 'text-green' : 'text-red'}>
                  {app.engine_decision}
                </strong>
              </div>
              <div className="app-notes"><strong>Purpose:</strong> {app.purpose}</div>
            </div>
            <div className="app-actions">
              <button
                onClick={() => handleDecision(app.id, 'approved', 'Approved based on score')}
                className="btn-approve"
                disabled={deciding === app.id}
              >
                <CheckCircle size={16} /> Approve
              </button>
              <button
                onClick={() => handleDecision(app.id, 'rejected', 'Insufficient buffer')}
                className="btn-reject"
                disabled={deciding === app.id}
              >
                <XCircle size={16} /> Reject
              </button>
            </div>
          </div>
        ))}
        {apps.length === 0 && !error && <div className="empty-state">No pending applications.</div>}
      </div>
    </div>
  );
}
