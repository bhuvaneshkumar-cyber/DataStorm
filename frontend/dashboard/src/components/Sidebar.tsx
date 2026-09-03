import { useEffect, useRef, useCallback, useState } from 'react';
import {
  ArrowLeftRight,
  CreditCard,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Sparkles,
  User,
  Wallet,
  X,
} from 'lucide-react';

type NavItem = {
  id: string;
  label: string;
  icon: React.ReactNode;
};

const mainNavItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} strokeWidth={1.8} /> },
  { id: 'stash', label: 'Stash', icon: <Wallet size={18} strokeWidth={1.8} /> },
  { id: 'transactions', label: 'Transactions', icon: <ArrowLeftRight size={18} strokeWidth={1.8} /> },
  { id: 'credit', label: 'Credit', icon: <CreditCard size={18} strokeWidth={1.8} /> },
  { id: 'ai-insights', label: 'AI Insights', icon: <Sparkles size={18} strokeWidth={1.8} /> },
  { id: 'resilience', label: 'Resilience', icon: <ShieldCheck size={18} strokeWidth={1.8} /> },
];

const bottomNavItems: NavItem[] = [
  { id: 'settings', label: 'Settings', icon: <Settings size={18} strokeWidth={1.8} /> },
  { id: 'profile', label: 'Profile', icon: <User size={18} strokeWidth={1.8} /> },
];

type SidebarProps = {
  open: boolean;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLElement | null>;
};

export default function Sidebar({ open, onClose, triggerRef }: SidebarProps) {
  const [activeItem, setActiveItem] = useState('dashboard');
  const [closing, setClosing] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);

  // Smooth close with animation
  const handleClose = useCallback(() => {
    setClosing(true);
    const timer = window.setTimeout(() => {
      setClosing(false);
      onClose();
      // Return focus to the Bryn trigger
      triggerRef.current?.focus();
    }, 200); // matches sidebar-out animation duration
    return () => window.clearTimeout(timer);
  }, [onClose, triggerRef]);

  // Escape key closes sidebar
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, handleClose]);

  // Move focus into sidebar when it opens
  useEffect(() => {
    if (open && !closing) {
      // Small delay to let the animation start before focusing
      const timer = window.setTimeout(() => {
        firstItemRef.current?.focus();
      }, 50);
      return () => window.clearTimeout(timer);
    }
  }, [open, closing]);

  if (!open) return null;

  const handleNavClick = (id: string) => {
    setActiveItem(id);
    // On mobile, close sidebar when a nav item is clicked
    if (window.innerWidth <= 760) {
      handleClose();
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={`sidebar-backdrop${closing ? ' sidebar-closing' : ''}`}
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Sidebar panel */}
      <nav
        ref={sidebarRef}
        className={`sidebar${closing ? ' sidebar-closing' : ''}`}
        role="navigation"
        aria-label="Main navigation"
      >
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="brand-symbol" aria-hidden="true">
              <ShieldCheck size={18} strokeWidth={2.5} />
            </div>
            <span>Bryn</span>
          </div>
          <button
            className="sidebar-close"
            type="button"
            onClick={handleClose}
            aria-label="Close navigation"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        {/* Main navigation */}
        <div className="sidebar-nav">
          <div className="sidebar-section">
            {mainNavItems.map((item, index) => (
              <button
                key={item.id}
                ref={index === 0 ? firstItemRef : undefined}
                className={`sidebar-item${activeItem === item.id ? ' active' : ''}`}
                type="button"
                onClick={() => handleNavClick(item.id)}
                aria-current={activeItem === item.id ? 'page' : undefined}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {/* Bottom section */}
        <div className="sidebar-bottom">
          {bottomNavItems.map((item) => (
            <button
              key={item.id}
              className={`sidebar-item${activeItem === item.id ? ' active' : ''}`}
              type="button"
              onClick={() => handleNavClick(item.id)}
              aria-current={activeItem === item.id ? 'page' : undefined}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      </nav>
    </>
  );
}
