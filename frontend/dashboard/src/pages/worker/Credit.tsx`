import { useEffect, useState } from 'react';
import { fetchMyCreditProfile, analyzeStatement } from '@/lib/api';
import { Gauge, Upload, Info, AlertCircle } from 'lucide-react';

export default function Credit() {
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchMyCreditProfile().then(setProfile).finally(() => setLoading(false));
  }, []);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await analyzeStatement(file);
      setProfile(res.score); // Simple update, real app would update the profile record
      alert('Statement analysed successfully!');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <div className="loading">Loading Credit Analysis...</div>;

  return (
    <div className="credit-page">
      <div className="score-hero">
        <div className="score-circle">
          <Gauge size={48} />
          <div className="score-value">{profile?.final_score || '---'}</div>
          <div className="score-label">{profile?.category || 'Analyzing...'}</div>
        </div>
        <div className="score-info">
          <h2>Alternative Credit Score</h2>
          <p>Your score is built on your actual work behavior, not just a bureau record.</p>
          <div className="assumptions-box">
            <strong>Note:</strong> {profile?.assumptions?.join(' ') || 'No assumptions made.'}
          </div>
        </div>
      </div>

      <div className="upload-card">
        <h3>Update Your Score</h3>
        <p>Upload a bank statement or platform payout PDF to refine your credit profile.</p>
        <form onSubmit={handleUpload} className="upload-form">
          <input type="file" accept=".pdf,.csv,.xlsx" onChange={e => setFile(e.target.files?.[0] || null)} required />
          <button type="submit" disabled={uploading || !file} className="primary-button">
            {uploading ? 'Processing...' : 'Upload & Analyse'}
          </button>
        </form>
        {error && <div className="error-msg">{error}</div>}
      </div>
    </div>
  );
}
