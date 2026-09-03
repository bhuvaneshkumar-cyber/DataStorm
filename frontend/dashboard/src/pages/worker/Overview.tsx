import { useEffect, useState } from 'react';
import { fetchDashboard, fetchMyCreditProfile, DashboardData, CreditProfile } from '@/lib/api';
import { Wallet, TrendingUp, ShieldCheck, ArrowRight, Zap, AlertCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useNavigate } from 'react-router-dom';

export default function Overview() {
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [score, setScore] = useState<CreditProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([fetchDashboard(), fetchMyCreditProfile()])
      .then(([d, s]) => {
        setDash(d);
        setScore(s);
      })
      .catch(() => setError('Failed to load financial data. Please refresh.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Initializing Command Center...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!dash) return <div className="error">Failed to load financial data. Please refresh.</div>;

  const baseline = dash.income_30d_baseline ?? 0;
  const chartData = [
    { name: 'Week 1', amount: baseline * 0.9 },
    { name: 'Week 2', amount: baseline * 1.1 },
    { name: 'Week 3', amount: baseline * 0.8 },
    { name: 'Week 4', amount: baseline * 1.2 },
  ];

  const isHighVolatility = (dash.volatility_index ?? 0) > 0.3;

  return (
    <div className="overview-page">
      <div className="overview-grid">
        <div className="stat-card highlight">
          <div className="stat-header">
            <Wallet size={24} />
            <h3>Resilience Stash</h3>
          </div>
          <div className="stat-value">₹{dash.total_stash_balance?.toLocaleString() ?? '0'}</div>
          <div className="stat-sub">Secure buffer for lean weeks</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <TrendingUp size={24} />
            <h3>Weekly Baseline</h3>
          </div>
          <div className="stat-value">₹{baseline.toLocaleString()}</div>
          <div className="stat-sub">Average verified payout</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <ShieldCheck size={24} />
            <h3>Behavioral Score</h3>
          </div>
          <div className="stat-value">{score?.final_score ?? 'N/A'}</div>
          <div className="stat-sub">{score?.category ?? 'Analyzing...'}</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <Zap size={24} />
            <h3>Eligible Loan</h3>
          </div>
          <div className="stat-value">Ready</div>
          <div className="stat-sub">Based on current profile</div>
        </div>
      </div>

      <div className="dashboard-layout">
        <div className="main-col">
          <div className="card">
            <div className="card-title">
              <TrendingUp size={18} />
              <span>Income Volatility Trend</span>
            </div>
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <Tooltip
                    cursor={{ fill: '#f1f5f9' }}
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                  />
                  <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                    {chartData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={index === 3 ? '#4f46e5' : '#818cf8'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="recent-activity">
            <div className="card-title">
              <Zap size={18} />
              <span>Recent Stash Sweeps</span>
            </div>
            <div className="activity-list">
              {dash.recent_sweeps?.length ? (
                dash.recent_sweeps.map(s => (
                  <div key={s.id} className="activity-item">
                    <div className="item-info">
                      <strong>{s.reason}</strong>
                      <span>{s.created_at ? new Date(s.created_at).toLocaleDateString() : 'Recently'}</span>
                    </div>
                    <div className="item-amount">+₹{s.sweep_amount?.toLocaleString()}</div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No recent sweeps found.</div>
              )}
            </div>
          </div>
        </div>

        <div className="side-col">
          <div className="card">
            <div className="card-title">Quick Actions</div>
            <div className="action-list">
              <button onClick={() => navigate('/expenses')} className="action-btn">
                <ArrowRight size={16} /> Log Expense
              </button>
              <button onClick={() => navigate('/loans')} className="action-btn">
                <ArrowRight size={16} /> Apply for Loan
              </button>
              <button onClick={() => navigate('/tax')} className="action-btn">
                <ArrowRight size={16} /> Review Tax
              </button>
              <button onClick={() => navigate('/bot')} className="action-btn">
                <ArrowRight size={16} /> Ask Policy Bot
              </button>
            </div>
          </div>

          <div className="card alert-card">
            <div className="card-title">
              <AlertCircle size={18} color="#f59e0b" />
              <span>Insight</span>
            </div>
            <p className="insight-text">
              Your income volatility is {isHighVolatility ? 'High' : 'Stable'}.
              {isHighVolatility
                ? ' We recommend increasing your stash buffer.'
                : ' Your resilience is on track.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
