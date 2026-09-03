import { Link, useLocation } from 'react-router-dom';
import { LucideIcon } from 'lucide-react';

type NavItem = {
  label: string;
  icon: LucideIcon;
  path: string;
};

type SidebarProps = {
  brandName: string;
  brandLogo: string;
  brandColor: string;
  navItems: NavItem[];
  user: any;
  onLogout: () => void;
};

export default function Sidebar({ brandName, brandLogo, brandColor, navItems, user, onLogout }: SidebarProps) {
  const location = useLocation();

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo" style={{ backgroundColor: brandColor }}>{brandLogo}</div>
        <h2>{brandName}</h2>
      </div>
      <nav className="nav-list">
        {navItems.map((item, i) => {
          const isActive = location.pathname === item.path;
          const Icon = item.icon;
          return (
            <Link
              key={i}
              to={item.path}
              className={`nav-item ${isActive ? 'active' : ''}`}
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
            {user?.name?.[0] || 'U'}
          </div>
          <span>{user?.name || 'User'}</span>
        </div>
        <button onClick={onLogout} className="logout-btn">
          <span className="logout-icon">→</span>
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
}
