import { Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import { User } from '@/lib/api';

interface LenderLayoutProps {
  user: User;
  setUser: (u: User | null) => void;
}

const NAV_ITEMS = [
  { label: 'Dashboard', icon: LayoutDashboard, path: '/lender' },
];

export default function LenderLayout({ user, setUser }: LenderLayoutProps) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    navigate('/login');
  };

  return (
    <div className="worker-shell">
      <Sidebar
        brandName="Lender Portal"
        brandLogo="L"
        brandColor="#f59e0b"
        navItems={NAV_ITEMS}
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
