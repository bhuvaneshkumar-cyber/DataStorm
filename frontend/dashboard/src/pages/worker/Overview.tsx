import { useEffect, useState } from 'react';
import { fetchDashboard, fetchCreditScore } from '@/lib/api';
import { Wallet, TrendingUp, ShieldCheck, ArrowUpRight } from 'lucide-react';

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchDashboard(), fetchCreditScore({
      age: 30, primary_gig_platform: 'Other', platform_customer_rating: 4,
      completed_gigs_per_week: 10, average_weekly_payout: 5000,
      payout_volatility_index: 0.2, active_platform_hours_per_week: 40,
      resilience_stash_balance: 0
    })]).then(([dash, score]) => {
      setData({ dash, score });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Loading Overview...</div>;
  if (!data) return <div className="error">Failed to load dashboard data.</div>;

  return (
    <div className="overview-grid">
      <div className="stat-card highlight">
        <div className="stat-header">
          <Wallet size={24} />
          <h3>Resilience Stash</h3>
        </div>
        <div className="stat-value">₹{data.dash?.total_stash_balance?.toLocaleString() || '0'}</div>
        <div className="stat-sub">Total saved for lean weeks</div>
      </div>

      <div className="stat-card">
        <div className="stat-header">
          <TrendingUp size={24} />
          <h3>30D Baseline</h3>
        </div>
        <div className="stat-value">₹{data.dash?.income_30d_baseline?.toLocaleString() || '0'}</div>
        <div className="stat-sub">Avg. weekly payout</div>
      </div>

      <div className="stat-card">
        <div className="stat-header">
          <ShieldCheck size={24} />
          <h3>Credit Score</h3>
        </div>
        <div className="stat-value">{data.score?.final_score || 'N/A'}</div>
        <div className="stat-sub">{data.score?.category || 'Unknown'}</div>
      </div>

      <div className="recent-activity">
        <h3>Recent Sweeps</h3>
        <div className="activity-list">
          {data.dash?.recent_sweeps?.map((s: any) => (
            <div key={s.id} className="activity-item">
              <div className="item-info">
                <strong>{s.reason}</strong>
                <span>{s.created_at ? new Date(s.created_at).toLocaleDateString() : 'Recently'}</span>
              </div>
              <div className="item-amount">+₹{s.sweep_amount}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
