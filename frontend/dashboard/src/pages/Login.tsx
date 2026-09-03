import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { login } from '@/lib/api';

export default function Login({ setUser }: { setUser: (u: any) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('worker');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      const res = await login({ email, password, expected_role: role });
      setUser(res.user);
      navigate(role === 'lender' ? '/lender' : '/');
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>Welcome back</h1>
        <p>Sign in to manage your financial resilience</p>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          <div className="field">
            <label>I am a...</label>
            <select value={role} onChange={e => setRole(e.target.value)}>
              <option value="worker">Gig Worker</option>
              <option value="lender">Verified Lender</option>
            </select>
          </div>
          {error && <div className="error-msg">{error}</div>}
          <button type="submit" className="primary-button">Sign In</button>
        </form>
        <p className="auth-footer">
          Don't have an account? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  );
}
