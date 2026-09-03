import { useEffect, useState } from 'react';
import { fetchTaxSummary, TaxSummary } from '@/lib/api';
import { FileText, AlertCircle, Calculator, Calendar } from 'lucide-react';

export default function Tax() {
  const [summary, setSummary] = useState<TaxSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchTaxSummary()
      .then(setSummary)
      .catch(() => setError('Failed to load tax data.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Calculating tax liabilities...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!summary) return <div className="error">Failed to load tax data.</div>;

  return (
    <div className="tax-page">
      <div className="tax-hero">
        <FileText size={48} color="var(--primary)" />
        <h2 className="tax-hero-title">Tax Liability Snapshot</h2>
        <p className="tax-hero-sub">
          Automated presumptive taxation estimate under Section 44AD of the Income Tax Act.
        </p>
      </div>

      <div className="tax-grid">
        <div className="tax-main">
          <div className="tax-card">
            <div className="tax-label">ESTIMATED TOTAL TAX</div>
            <div className="tax-value">₹{summary.total_tax?.toLocaleString()}</div>
            <div className="tax-sub">Financial Year: {summary.financial_year}</div>
          </div>

          <div className="card">
            <div className="card-title"><Calculator size={18} /> Calculation Breakdown</div>
            <div className="tax-details">
              <div className="detail-row">
                <span>Annualised Gross Income</span>
                <strong>₹{summary.annualised_gross_income?.toLocaleString()}</strong>
              </div>
              <div className="detail-row">
                <span>Presumptive Taxable Income (6%/8%)</span>
                <strong>₹{summary.taxable_income?.toLocaleString()}</strong>
              </div>
              <div className="detail-row detail-row-last">
                <span className="detail-row-highlight">Monthly Set-aside Recommendation</span>
                <strong className="text-highlight">₹{summary.monthly_set_aside?.toLocaleString()}</strong>
              </div>
            </div>
          </div>
        </div>

        <div className="side-col">
          <div className="card">
            <div className="card-title"><Calendar size={18} /> Compliance Notes</div>
            <ul className="notes-list">
              {summary.notes?.map((n, i) => (
                <li key={i} className="note-item">{n}</li>
              ))}
            </ul>
            {summary.gst_registration_required && (
              <div className="gst-alert">
                <AlertCircle size={18} />
                <div>
                  <strong className="gst-alert-title">GST Registration Required</strong>
                  <span className="gst-alert-sub">Your turnover exceeds the mandatory threshold.</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
