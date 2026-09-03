import { Link, useLocation } from 'react-router-dom';
import { LucideIcon } from 'lucide-react';
import { User } from '@/lib/api';

interface NavItem {
  label: string;
  icon: LucideIcon;
  path: string;
}

interface SidebarProps {
  brandName: string;
  brandLogo: string;
  brandColor: string;
  navItems: NavItem[];
  user: User;
  onLogout: () => void;
}

export default function Sidebar({ brandName, brandLogo, brandColor, navItems, user, onLogout }: SidebarProps) {
  const location = useLocation();

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo" style={{ backgroundColor: brandColor }}>{brandLogo}</div>
        <h2>{brandName}</h2>
      </div>

      <nav className="nav-list">
        {navItems.map(item => {
          const isActive = location.pathname === item.path;
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item${isActive ? ' active' : ''}`}
            >
              <Icon size={20} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="user-info">
          <div className="avatar" style={{ backgroundColor: brandColor }}>
            {user.name?.[0]?.toUpperCase() ?? 'U'}
          </div>
          <span>{user.name}</span>
        </div>
        <button onClick={onLogout} className="logout-btn">
          <span className="logout-icon">→</span>
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
}
