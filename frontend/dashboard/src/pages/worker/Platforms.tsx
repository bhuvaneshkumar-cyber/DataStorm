import { useEffect, useState } from 'react';
import { fetchPlatforms, connectPlatform, disconnectPlatform, PlatformAccount } from '@/lib/api';
import { Trash2, CheckCircle, AlertCircle } from 'lucide-react';

interface PlatformForm {
  platform: string;
  account_handle: string;
  customer_rating: string;
  weekly_payout: string;
  gigs_per_week: string;
  hours_per_week: string;
}

const EMPTY_FORM: PlatformForm = {
  platform: '',
  account_handle: '',
  customer_rating: '',
  weekly_payout: '',
  gigs_per_week: '',
  hours_per_week: '',
};

export default function Platforms() {
  const [platforms, setPlatforms] = useState<PlatformAccount[]>([]);
  const [form, setForm] = useState<PlatformForm>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [connectError, setConnectError] = useState('');
  const [disconnecting, setDisconnecting] = useState<string | null>(null);

  useEffect(() => {
    fetchPlatforms()
      .then(setPlatforms)
      .finally(() => setLoading(false));
  }, []);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnectError('');
    setSubmitting(true);
    try {
      await connectPlatform({
        platform: form.platform,
        account_handle: form.account_handle || undefined,
        customer_rating: form.customer_rating ? parseFloat(form.customer_rating) : undefined,
        weekly_payout: form.weekly_payout ? parseFloat(form.weekly_payout) : undefined,
        gigs_per_week: form.gigs_per_week ? parseFloat(form.gigs_per_week) : undefined,
        hours_per_week: form.hours_per_week ? parseFloat(form.hours_per_week) : undefined,
      });
      setForm(EMPTY_FORM);
      const updated = await fetchPlatforms();
      setPlatforms(updated);
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : 'Failed to connect platform.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDisconnect = async (id: string) => {
    setDisconnecting(id);
    try {
      await disconnectPlatform(id);
      setPlatforms(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      // Surface error inline rather than via confirm/alert
      setConnectError(err instanceof Error ? err.message : 'Failed to disconnect platform.');
    } finally {
      setDisconnecting(null);
    }
  };

  if (loading) return <div className="loading">Loading Platforms...</div>;

  return (
    <div className="platforms-page">
      <div className="side-col">
        <div className="card connect-section">
          <div className="card-title">Connect New Platform</div>
          {connectError && <div className="error-msg">{connectError}</div>}
          <form onSubmit={handleConnect} className="platform-form">
            <div className="field">
              <label>Platform Name</label>
              <input
                type="text"
                value={form.platform}
                onChange={e => setForm({ ...form, platform: e.target.value })}
                placeholder="e.g. Uber, Swiggy"
                required
              />
            </div>
            <div className="field">
              <label>Handle / ID</label>
              <input
                type="text"
                value={form.account_handle}
                onChange={e => setForm({ ...form, account_handle: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Rating (1–5)</label>
              <input
                type="number"
                step="0.1"
                min="1"
                max="5"
                value={form.customer_rating}
                onChange={e => setForm({ ...form, customer_rating: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Weekly Payout (₹)</label>
              <input
                type="number"
                value={form.weekly_payout}
                onChange={e => setForm({ ...form, weekly_payout: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Gigs / Week</label>
              <input
                type="number"
                value={form.gigs_per_week}
                onChange={e => setForm({ ...form, gigs_per_week: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Hours / Week</label>
              <input
                type="number"
                value={form.hours_per_week}
                onChange={e => setForm({ ...form, hours_per_week: e.target.value })}
              />
            </div>
            <button type="submit" className="primary-button" disabled={submitting}>
              {submitting ? 'Connecting...' : 'Connect Platform'}
            </button>
          </form>
        </div>
      </div>

      <div className="main-col">
        <div className="platforms-list">
          <div className="card-title">Your Connected Platforms</div>
          <div className="platform-grid">
            {platforms.map(p => (
              <div key={p.id} className="platform-card">
                <div className="card-top">
                  <strong>{p.platform}</strong>
                  {p.verified
                    ? <CheckCircle size={16} className="text-green" />
                    : <AlertCircle size={16} className="text-orange" />}
                </div>
                <div className="card-body">
                  <div>Rating: {p.customer_rating ?? 'N/A'}</div>
                  <div>Payout: ₹{p.weekly_payout ?? '0'} /wk</div>
                  <div>Hours: {p.hours_per_week ?? '0'} /wk</div>
                </div>
                <button
                  onClick={() => handleDisconnect(p.id)}
                  className="disconnect-btn"
                  disabled={disconnecting === p.id}
                >
                  <Trash2 size={16} />
                  {disconnecting === p.id ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </div>
            ))}
            {platforms.length === 0 && (
              <div className="empty-state">No platforms connected yet. Add one to get started.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
