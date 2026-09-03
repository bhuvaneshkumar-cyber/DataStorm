/**
 * The frame every signed-in screen renders inside: header, navigation, and the
 * policy bot.
 *
 * The navigation is built from the signed-in role, so the lender portal and the
 * worker app are the same shell with a different route list rather than two
 * parallel layouts that drift apart.
 */

import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Building2,
  CreditCard,
  FileSpreadsheet,
  HandCoins,
  LayoutDashboard,
  LogOut,
  Menu,
  Receipt,
  Settings,
  ShieldCheck,
  Umbrella,
  Wallet,
  X,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthContext';
import { useI18n } from '@/i18n';
import { initialsOf } from '@/lib/format';
import PolicyBot from './PolicyBot';
import type { StringKey } from '@/i18n';
import type { Role } from '@/lib/types';

type NavEntry = { to: string; labelKey: StringKey; icon: React.ReactNode };

const ICON = { size: 18, strokeWidth: 1.8 } as const;

const WORKER_NAV: NavEntry[] = [
  { to: '/dashboard', labelKey: 'nav.dashboard', icon: <LayoutDashboard {...ICON} /> },
  { to: '/expenses', labelKey: 'nav.expenses', icon: <Wallet {...ICON} /> },
  { to: '/platforms', labelKey: 'nav.platforms', icon: <Building2 {...ICON} /> },
  { to: '/credit', labelKey: 'nav.credit', icon: <CreditCard {...ICON} /> },
  { to: '/loans', labelKey: 'nav.loans', icon: <HandCoins {...ICON} /> },
  { to: '/insurance', labelKey: 'nav.insurance', icon: <Umbrella {...ICON} /> },
  { to: '/tax', labelKey: 'nav.tax', icon: <Receipt {...ICON} /> },
  { to: '/financials', labelKey: 'nav.financials', icon: <FileSpreadsheet {...ICON} /> },
];

const LENDER_NAV: NavEntry[] = [
  { to: '/lender', labelKey: 'nav.lenderQueue', icon: <HandCoins {...ICON} /> },
];

const NAV_FOR: Record<Role, NavEntry[]> = { worker: WORKER_NAV, lender: LENDER_NAV };

export default function AppShell() {
  const { user, signOut } = useAuth();
  const { t } = useI18n();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  // Navigating closes the drawer. Without this it stays open over the page the
  // reader just asked for, on exactly the narrow screens where it covers it.
  useEffect(() => setNavOpen(false), [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setNavOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [navOpen]);

  if (!user) return null;

  const entries = NAV_FOR[user.role];

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-inner">
          <button
            ref={menuButtonRef}
            type="button"
            className="icon-button nav-toggle"
            aria-label="Toggle navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen((open) => !open)}
          >
            {navOpen ? <X size={18} /> : <Menu size={18} />}
          </button>

          <div className="brand-mark">
            <span className="brand-symbol" aria-hidden="true">
              <ShieldCheck size={17} strokeWidth={2.4} />
            </span>
            <span className="brand-word">{t('app.name')}</span>
          </div>

          <div className="header-identity">
            <span className="avatar" aria-hidden="true">
              {initialsOf(user.name)}
            </span>
            <div className="identity-text">
              <strong>{user.name}</strong>
              <span>{user.role === 'lender' ? t('auth.lenderPortal') : user.email}</span>
            </div>
            <button type="button" className="ghost-button" onClick={signOut}>
              <LogOut size={14} strokeWidth={1.9} aria-hidden="true" />
              {t('nav.signOut')}
            </button>
          </div>
        </div>
      </header>

      <div className="app-body">
        {navOpen && (
          <div className="nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />
        )}

        <nav className={`app-nav${navOpen ? ' open' : ''}`} aria-label="Main navigation">
          <div className="nav-section">
            {entries.map((entry) => (
              <NavLink
                key={entry.to}
                to={entry.to}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                end={entry.to === '/lender'}
              >
                {entry.icon}
                {t(entry.labelKey)}
              </NavLink>
            ))}
          </div>
          <div className="nav-section nav-bottom">
            <NavLink
              to="/settings"
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Settings {...ICON} />
              {t('nav.settings')}
            </NavLink>
          </div>
        </nav>

        <main className="app-main">
          <Outlet />
        </main>
      </div>

      {/* Available on every protected route, which is where a question about
          policy actually occurs to someone. */}
      <PolicyBot />
    </div>
  );
}
