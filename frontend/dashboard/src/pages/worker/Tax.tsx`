import { useEffect, useState } from 'react';
import { fetchTaxSummary } from '@/lib/api';
import { FileText, AlertCircle } from 'lucide-react';

export default function Tax() {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTaxSummary().then(setSummary).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Loading Tax Summary...</div>;
  if (!summary) return <div className="error">Failed to load tax data.</div>;

  return (
    <div className="tax-page">
      <div className="tax-hero">
        <FileText size={48} />
        <h2>Tax Liability Snapshot</h2>
        <p>Automated estimate based on your logged gig income.</p>
      </div>

      <div className="tax-grid">
        <div className="tax-main">
          <div className="tax-card">
            <h3>Annualized Estimate</h3>
            <div className="tax-value">₹{summary.total_tax?.toLocaleString()}</div>
            <div className="tax-sub">Estimated Total Tax for {summary.financial_year}</div>
          </div>

          <div className="tax-details">
            <h4>Breakdown</h4>
            <div className="detail-row">
              <span>Gross Income (Annualised)</span>
              <strong>₹{summary.annualised_gross_income?.toLocaleString()}</strong>
            </div>
            <div className="detail-row">
              <span>Taxable Income (after 44AD)</span>
              <strong>₹{summary.taxable_income?.toLocaleString()}</strong>
            </div>
            <div className="detail-row">
              <span>Monthly Set-aside</strong>
              <strong className="text-highlight">₹{summary.monthly_set_aside?.toLocaleString()}</strong>
            </div>
          </div>
        </div>

        <div className="tax-sidebar">
          <div className="notes-card">
            <h3>Important Notes</h3>
            <ul>
              {summary.notes?.map((n: string, i: number) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
            {summary.gst_registration_required && (
              <div className="gst-alert">
                <AlertCircle size={16} />
                <span>GST Registration Required!</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
