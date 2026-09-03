import { Outlet, Link, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Wallet,
  ArrowLeftRight,
  CreditCard,
  ShieldCheck,
  FileText,
  HeartPulse,
  MessageSquare,
  LogOut,
  User
} from 'lucide-react';

export default function WorkerLayout({ user, setUser }: { user: any, setUser: (u: any) => void }) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    navigate('/login');
  };

  const navItems = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={20} />, path: '/' },
    { id: 'expenses', label: 'Expenses', icon: <ArrowLeftRight size={20} />, path: '/expenses' },
    { id: 'platforms', label: 'Platforms', icon: <Wallet size={20} />, path: '/platforms' },
    { id: 'credit', label: 'Credit', icon: <CreditCard size={20} />, path: '/credit' },
    { id: 'loans', label: 'Loans', icon: <HeartPulse size={20} />, path: '/loans' },
    { id: 'insurance', label: 'Insurance', icon: <ShieldCheck size={20} />, path: '/insurance' },
    { id: 'tax', label: 'Tax', icon: <FileText size={20} />, path: '/tax' },
    { id: 'bot', label: 'Policy Bot', icon: <MessageSquare size={20} />, path: '/bot' },
  ];

  return (
    <div className="worker-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">DS</div>
          <h2>DataStorm</h2>
        </div>
        <nav className="nav-list">
          {navItems.map(item => (
            <Link key={item.id} to={item.path} className="nav-item">
              {item.icon}
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="avatar">{user.name?.[0] || 'U'}</div>
            <span>{user.name || 'User'}</span>
          </div>
          <button onClick={handleLogout} className="logout-btn">
            <LogOut size={18} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
      <main className="main-content">
        <header className="top-bar">
          <h1>Financial Resilience Center</h1>
          <div className="top-actions">
             <span>Welcome, {user.name}</span>
          </div>
        </header>
        <div className="page-body">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
