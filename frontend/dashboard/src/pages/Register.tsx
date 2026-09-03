import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { register } from '@/lib/api';

export default function Register({ setUser }: { setUser: (u: any) => void }) {
  const [form, setForm] = useState({
    name: '', email: '', password: '', phone: '', role: 'worker', language: 'en', employment_type: ''
  });
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      const res = await register(form);
      setUser(res.user);
      navigate(form.role === 'lender' ? '/lender' : '/');
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>Join DataStorm</h1>
        <p>Build your financial resilience today</p>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Full Name</label>
            <input type="text" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required />
          </div>
          <div className="field">
            <label>Email</label>
            <input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required />
          </div>
          <div className="field">
            <label>Phone</label>
            <input type="tel" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
          </div>
          <div className="field">
            <label>Role</label>
            <select value={form.role} onChange={e => setForm({...form, role: e.target.value})}>
              <option value="worker">Gig Worker</option>
              <option value="lender">Verified Lender</option>
            </select>
          </div>
          <div className="field">
            <label>Language</label>
            <select value={form.language} onChange={e => setForm({...form, language: e.target.value})}>
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="ta">Tamil</option>
            </select>
          </div>
          {error && <div className="error-msg">{error}</div>}
          <button type="submit" className="primary-button">Register</button>
        </form>
        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign In</Link>
        </p>
      </div>
    </div>
  );
}
