import { useEffect, useState } from 'react';
import { fetchInsuranceRecommendations } from '@/lib/api';
import { ShieldCheck, Info, AlertCircle } from 'lucide-react';

export default function Insurance() {
  const [recs, setRecs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchInsuranceRecommendations().then(setRecs).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Loading Insurance Recommendations...</div>;

  return (
    <div className="insurance-page">
      <div className="hero">
        <ShieldCheck size={48} />
        <h2>Micro-Insurance Recommendations</h2>
        <p>Tailored coverage based on your income volatility and risk profile.</p>
      </div>

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
            <button className="secondary-button">Learn More & Apply</button>
          </div>
        ))}
        {recs.length === 0 && <div className="empty">No recommendations available at this time.</div>}
      </div>
    </div>
  );
}
