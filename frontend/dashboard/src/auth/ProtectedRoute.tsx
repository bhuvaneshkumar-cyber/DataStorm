/**
 * Route guards.
 *
 * These are a usability layer, not a security boundary: the real enforcement is
 * the role check on every API route. What they buy is that a lender never sees
 * an empty worker dashboard, and a signed-out visitor lands on the right sign-in
 * page for where they were trying to go.
 */

import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';
import Spinner from '@/components/Spinner';
import type { Role } from '@/lib/types';

/** Where each role belongs when it turns up somewhere it does not. */
const HOME_FOR: Record<Role, string> = {
  worker: '/dashboard',
  lender: '/lender',
};

export function RequireAuth({ role }: { role?: Role }) {
  const { user, initialising } = useAuth();
  const location = useLocation();

  // Waiting on the token check. Redirecting now would bounce a signed-in user
  // to the login screen on every hard refresh.
  if (initialising) return <Spinner full />;

  if (!user) {
    const signInPath = role === 'lender' ? '/lender/sign-in' : '/sign-in';
    // `state.from` is what sends someone back to the page they asked for once
    // they have signed in, rather than dumping them on the dashboard.
    return <Navigate to={signInPath} replace state={{ from: location }} />;
  }

  if (role && user.role !== role) return <Navigate to={HOME_FOR[user.role]} replace />;

  return <Outlet />;
}

/** Keeps a signed-in person out of the sign-in and registration screens. */
export function RedirectIfSignedIn() {
  const { user, initialising } = useAuth();

  if (initialising) return <Spinner full />;
  if (user) return <Navigate to={HOME_FOR[user.role]} replace />;

  return <Outlet />;
}

export { HOME_FOR };
