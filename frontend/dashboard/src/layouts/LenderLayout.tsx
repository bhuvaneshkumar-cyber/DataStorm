import { Outlet, Link, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Wallet, ArrowLeftRight, CreditCard, ShieldCheck, FileText, HeartPulse, MessageSquare, LogOut, User } from 'lucide-react';

export default function LenderLayout({ user, setUser }: { user: any, setUser: (u: any) => void }) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    navigate('/login');
  };

  return (
    <div className="worker-shell">
      <aside className="sidebar lender-sidebar">
        <div className="brand">
          <div className="logo lender-logo">L</div>
          <h2>Lender Portal</h2>
        </div>
        <nav className="nav-list">
          <Link to="/lender" className="nav-item">
            <LayoutDashboard size={20} />
            <span>Dashboard</span>
          </Link>
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="avatar">{user.name?.[0] || 'L'}</div>
            <span>{user.name || 'Lender'}</span>
          </div>
          <button onClick={handleLogout} className="logout-btn">
            <LogOut size={18} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
      <main className="main-content">
        <header className="top-bar">
          <h1>Lender Management Console</h1>
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
