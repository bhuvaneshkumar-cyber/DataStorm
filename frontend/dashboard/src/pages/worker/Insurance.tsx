import { useEffect, useState } from 'react';
import { fetchInsuranceRecs, InsuranceRecommendation } from '@/lib/api';
import { ShieldCheck, Info } from 'lucide-react';

export default function Insurance() {
  const [recs, setRecs] = useState<InsuranceRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchInsuranceRecs()
      .then(setRecs)
      .catch(() => setError('Failed to load recommendations.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Loading Insurance Recommendations...</div>;

  return (
    <div className="insurance-page">
      <div className="hero">
        <ShieldCheck size={48} />
        <h2>Micro-Insurance Recommendations</h2>
        <p>Tailored coverage based on your income volatility and risk profile.</p>
      </div>

      {error && <div className="error-msg">{error}</div>}

      <div className="recs-grid">
        {recs.map((rec, i) => (
          <div key={i} className="rec-card">
            <div className="rec-head">
              <strong>{rec.product_name}</strong>
              <span className="rec-priority">{rec.priority}</span>
            </div>
            <div className="rec-body">
              <p>{rec.description}</p>
              <div className="rec-price">Est. Premium: <strong>₹{rec.estimated_premium}/mo</strong></div>
              <div className="rec-benefit">
                <Info size={14} />
                <span>Key Benefit: {rec.primary_benefit}</span>
              </div>
            </div>
            <button className="secondary-button">Learn More &amp; Apply</button>
          </div>
        ))}
        {recs.length === 0 && !error && (
          <div className="empty-state">No recommendations available at this time.</div>
        )}
      </div>
    </div>
  );
}
