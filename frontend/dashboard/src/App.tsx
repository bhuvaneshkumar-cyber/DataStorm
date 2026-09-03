/**
 * The route table.
 *
 * Public routes, worker routes and lender routes are three groups, each behind
 * the guard that belongs to it. Reading this file should be enough to know who
 * can reach what.
 */

import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth, RedirectIfSignedIn } from '@/auth/ProtectedRoute';
import AppShell from '@/components/AppShell';
import Credit from '@/pages/Credit';
import Dashboard from '@/pages/Dashboard';
import Expenses from '@/pages/Expenses';
import Financials from '@/pages/Financials';
import Insurance from '@/pages/Insurance';
import LenderDashboard from '@/pages/LenderDashboard';
import Loans from '@/pages/Loans';
import Platforms from '@/pages/Platforms';
import Settings from '@/pages/Settings';
import SignIn from '@/pages/SignIn';
import SignUp from '@/pages/SignUp';
import Tax from '@/pages/Tax';
import { useI18n } from '@/i18n';

function NotFound() {
  const { t } = useI18n();
  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>404</h1>
        <p>{t('state.empty')}</p>
        <a className="primary-button wide" href="/">
          {t('nav.dashboard')}
        </a>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Public: signing in and registering. A signed-in visitor is bounced to
          their own home rather than being shown a login form they do not need. */}
      <Route element={<RedirectIfSignedIn />}>
        <Route path="/sign-in" element={<SignIn role="worker" />} />
        <Route path="/sign-up" element={<SignUp />} />
        <Route path="/lender/sign-in" element={<SignIn role="lender" />} />
      </Route>

      {/* Worker. Settings lives here rather than in a shared group because the
          lender shell has its own nav and no use for a language-only page. */}
      <Route element={<RequireAuth role="worker" />}>
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/expenses" element={<Expenses />} />
          <Route path="/platforms" element={<Platforms />} />
          <Route path="/credit" element={<Credit />} />
          <Route path="/loans" element={<Loans />} />
          <Route path="/insurance" element={<Insurance />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/financials" element={<Financials />} />
        </Route>
      </Route>

      {/* Lender. */}
      <Route element={<RequireAuth role="lender" />}>
        <Route element={<AppShell />}>
          <Route path="/lender" element={<LenderDashboard />} />
        </Route>
      </Route>

      {/* Settings is the one screen both roles share. */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
