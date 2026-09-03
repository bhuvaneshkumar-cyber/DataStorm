import { useEffect, useState } from 'react';
import { fetchPlatforms, connectPlatform, disconnectPlatform } from '@/lib/api';
import { Link, Trash2, CheckCircle, AlertCircle } from 'lucide-react';

export default function Platforms() {
  const [platforms, setPlatforms] = useState<any[]>([]);
  const [form, setForm] = useState({ platform: '', account_handle: '', customer_rating: '', weekly_payout: '', gigs_per_week: '', hours_per_week: '' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPlatforms().then(setPlatforms).finally(() => setLoading(false));
  }, []);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await connectPlatform({
        ...form,
        customer_rating: parseFloat(form.customer_rating),
        weekly_payout: parseFloat(form.weekly_payout),
        gigs_per_week: parseFloat(form.gigs_per_week),
        hours_per_week: parseFloat(form.hours_per_week),
      });
      setForm({ platform: '', account_handle: '', customer_rating: '', weekly_payout: '', gigs_per_week: '', hours_per_week: '' });
      const updated = await fetchPlatforms();
      setPlatforms(updated);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleDisconnect = async (id: string) => {
    if (!confirm('Disconnect this platform?')) return;
    await disconnectPlatform(id);
    const updated = await fetchPlatforms();
    setPlatforms(updated);
  };

  if (loading) return <div className="loading">Loading Platforms...</div>;

  return (
    <div className="platforms-page">
      <div className="connect-section">
        <h3>Connect New Platform</h3>
        <form onSubmit={handleConnect} className="platform-form">
          <div className="field">
            <label>Platform Name</label>
            <input type="text" value={form.platform} onChange={e => setForm({...form, platform: e.target.value})} placeholder="e.g. Uber, Swiggy" required />
          </div>
          <div className="field">
            <label>Handle/ID</label>
            <input type="text" value={form.account_handle} onChange={e => setForm({...form, account_handle: e.target.value})} />
          </div>
          <div className="field">
            <label>Rating (1-5)</label>
            <input type="number" step="0.1" value={form.customer_rating} onChange={e => setForm({...form, customer_rating: e.target.value})} />
          </div>
          <div className="field">
            <label>Weekly Payout</label>
            <input type="number" value={form.weekly_payout} onChange={e => setForm({...form, weekly_payout: e.target.value})} />
          </div>
          <div className="field">
            <label>Gigs/Week</label>
            <input type="number" value={form.gigs_per_week} onChange={e => setForm({...form, gigs_per_week: e.target.value})} />
          </div>
          <div className="field">
            <label>Hours/Week</label>
            <input type="number" value={form.hours_per_week} onChange={e => setForm({...form, hours_per_week: e.target.value})} />
          </div>
          <button type="submit" className="primary-button">Connect Platform</button>
        </form>
      </div>

      <div className="platforms-list">
        <h3>Your Connected Platforms</h3>
        <div className="platform-grid">
          {platforms.map(p => (
            <div key={p.id} className="platform-card">
              <div className="card-top">
                <strong>{p.platform}</strong>
                {p.verified ? <CheckCircle size={16} className="text-green" /> : <AlertCircle size={16} className="text-orange" />}
              </div>
              <div className="card-body">
                <div>Rating: {p.customer_rating || 'N/A'}</div>
                <div>Payout: ₹{p.weekly_payout || '0'} /wk</div>
                <div>Hours: {p.hours_per_week || '0'} /wk</div>
              </div>
              <button onClick={() => handleDisconnect(p.id)} className="disconnect-btn">
                <Trash2 size={16} /> Disconnect
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
