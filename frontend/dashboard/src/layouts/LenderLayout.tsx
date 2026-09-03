import { Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard } from 'lucide-react';
import Sidebar from '@/components/Sidebar';

export default function LenderLayout({ user, setUser }: { user: any, setUser: (u: any) => void }) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    navigate('/login');
  };

  const navItems = [
    { label: 'Dashboard', icon: LayoutDashboard, path: '/lender' },
  ];

  return (
    <div className="worker-shell">
      <Sidebar
        brandName="Lender Portal"
        brandLogo="L"
        brandColor="#f59e0b"
        navItems={navItems}
        user={user}
        onLogout={handleLogout}
      />
      <main className="main-content">
        <header className="top-bar">
          <h1 className="page-title">Lender Management Console</h1>
          <div className="top-actions">
             <span className="user-greeting">Welcome, {user.name}</span>
          </div>
        </header>
        <div className="page-body">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
