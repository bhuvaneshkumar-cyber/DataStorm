import { useEffect, useState } from 'react';
import { fetchMyCreditProfile, analyzeStatement, CreditProfile } from '@/lib/api';
import { Gauge, Upload, Info, TrendingUp } from 'lucide-react';

interface ResilienceFactor {
  label: string;
  level: string;
  percent: number;
}

const RESILIENCE_FACTORS: ResilienceFactor[] = [
  { label: 'Payout Consistency', level: 'High', percent: 85 },
  { label: 'Platform Rating', level: 'Excellent', percent: 92 },
  { label: 'Savings Ratio', level: 'Moderate', percent: 40 },
];

export default function Credit() {
  const [profile, setProfile] = useState<CreditProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [uploadSuccess, setUploadSuccess] = useState('');

  useEffect(() => {
    fetchMyCreditProfile()
      .then(setProfile)
      .finally(() => setLoading(false));
  }, []);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError('');
    setUploadSuccess('');
    try {
      const res = await analyzeStatement(file);
      setProfile(res.score);
      setUploadSuccess('Statement analyzed successfully! Your credit profile has been updated.');
      setFile(null);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Statement analysis failed.');
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <div className="loading">Analyzing credit profile...</div>;

  return (
    <div className="credit-page">
      <div className="score-hero">
        <div className="score-circle">
          <Gauge size={48} />
          <div className="score-value">{profile?.final_score ?? '---'}</div>
          <div className="score-label">{profile?.category ?? 'Analyzing...'}</div>
        </div>
        <div className="score-info">
          <h2 className="score-heading">Behavioral Credit Score</h2>
          <p className="score-description">
            Unlike traditional CIBIL scores, your DataStorm score is derived from your real-world gig behavior,
            payout consistency, and resilience buffer.
          </p>
          {profile?.assumptions && profile.assumptions.length > 0 && (
            <div className="assumptions-box">
              <div className="assumptions-label">
                <Info size={16} /> Analysis Logic
              </div>
              <p>{profile.assumptions.join(' ')}</p>
            </div>
          )}
        </div>
      </div>

      <div className="credit-details-grid">
        <div className="card">
          <div className="card-title"><TrendingUp size={18} /> Resilience Factors</div>
          <div className="factor-list">
            {RESILIENCE_FACTORS.map(f => (
              <div key={f.label} className="factor-item">
                <span className="factor-label">
                  {f.label} <span className="factor-level">{f.level}</span>
                </span>
                <div className="factor-bar-wrap">
                  <div className="factor-bar" style={{ width: `${f.percent}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="upload-card">
          <div className="card-title"><Upload size={18} /> Update Profile</div>
          <p className="upload-description">
            Upload your bank statements to unlock a higher credit limit and better loan rates.
          </p>
          <form onSubmit={handleUpload} className="upload-form">
            <input
              type="file"
              accept=".pdf,.csv,.xlsx"
              onChange={e => setFile(e.target.files?.[0] ?? null)}
              required
            />
            <button type="submit" disabled={uploading || !file} className="primary-button">
              {uploading ? 'Processing Statement...' : 'Upload & Analyse'}
            </button>
          </form>
          {uploadError && <div className="error-msg">{uploadError}</div>}
          {uploadSuccess && <div className="success-msg">{uploadSuccess}</div>}
        </div>
      </div>
    </div>
  );
}
