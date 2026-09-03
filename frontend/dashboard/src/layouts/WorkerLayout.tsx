import { Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Wallet,
  ArrowLeftRight,
  CreditCard,
  ShieldCheck,
  FileText,
  HeartPulse,
  MessageSquare,
} from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import { User } from '@/lib/api';

interface WorkerLayoutProps {
  user: User;
  setUser: (u: User | null) => void;
}

const NAV_ITEMS = [
  { label: 'Overview', icon: LayoutDashboard, path: '/' },
  { label: 'Expenses', icon: ArrowLeftRight, path: '/expenses' },
  { label: 'Platforms', icon: Wallet, path: '/platforms' },
  { label: 'Credit', icon: CreditCard, path: '/credit' },
  { label: 'Loans', icon: HeartPulse, path: '/loans' },
  { label: 'Insurance', icon: ShieldCheck, path: '/insurance' },
  { label: 'Tax', icon: FileText, path: '/tax' },
  { label: 'Policy Bot', icon: MessageSquare, path: '/bot' },
];

export default function WorkerLayout({ user, setUser }: WorkerLayoutProps) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    navigate('/login');
  };

  return (
    <div className="worker-shell">
      <Sidebar
        brandName="DataStorm"
        brandLogo="DS"
        brandColor="var(--primary)"
        navItems={NAV_ITEMS}
        user={user}
        onLogout={handleLogout}
      />
      <main className="main-content">
        <header className="top-bar">
          <h1 className="page-title">Financial Resilience Center</h1>
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
