import { useEffect, useState } from 'react';
import { fetchPendingLoans, decideLoan } from '@/lib/api';
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export default function LenderDashboard() {
  const [apps, setApps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPendingLoans().then(setApps).finally(() => setLoading(false));
  }, []);

  const handleDecision = async (appId: string, status: 'approved' | 'rejected', note: string) => {
    try {
      await decideLoan(appId, { status, lender_note: note });
      const updated = await fetchPendingLoans();
      setApps(updated);
    } catch (err: any) {
      alert(err.message);
    }
  };

  if (loading) return <div className="loading">Loading Applications...</div>;

  return (
    <div className="lender-page">
      <h2>Incoming Loan Applications</h2>
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
              <div className="app-row"><span>Decision:</span> <strong className={app.engine_decision === 'APPROVE' ? 'text-green' : 'text-red'}>{app.engine_decision}</strong></div>
              <div className="app-notes">
                <strong>Purpose:</strong> {app.purpose}
              </div>
            </div>
            <div className="app-actions">
              <button onClick={() => handleDecision(app.id, 'approved', 'Approved based on score')} className="btn-approve">
                <CheckCircle size={16} /> Approve
              </button>
              <button onClick={() => handleDecision(app.id, 'rejected', 'Insufficient buffer')} className="btn-reject">
                <XCircle size={16} /> Reject
              </button>
            </div>
          </div>
        ))}
        {apps.length === 0 && <div className="empty">No pending applications.</div>}
      </div>
    </div>
  );
}
