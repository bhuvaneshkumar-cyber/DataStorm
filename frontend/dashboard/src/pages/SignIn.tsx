/**
 * Sign in, for both audiences.
 *
 * One component serves the worker and lender doors, differing only in the role
 * it pins the request to. Two near-identical forms is how the lender page ends
 * up missing the fix the worker page got.
 */

import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { LogIn, ShieldCheck } from 'lucide-react';
import { useAuth } from '@/auth/AuthContext';
import { HOME_FOR } from '@/auth/ProtectedRoute';
import { useI18n, LANGUAGES } from '@/i18n';
import { useAction } from '@/lib/useAsync';
import { ErrorBanner, InlineSpinner } from '@/components/primitives';
import type { LanguageCode } from '@/i18n';
import type { Role } from '@/lib/types';

export default function SignIn({ role = 'worker' }: { role?: Role }) {
  const { signIn } = useAuth();
  const { t, language, setLanguage } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { run, busy, error } = useAction(signIn);

  const isLender = role === 'lender';

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const user = await run(email, password, role);
    if (!user) return;
    // Back to whatever they were trying to reach, or that role's home.
    const from = (location.state as { from?: Location } | null)?.from?.pathname;
    navigate(from ?? HOME_FOR[user.role], { replace: true });
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-symbol" aria-hidden="true">
            <ShieldCheck size={18} strokeWidth={2.4} />
          </span>
          <div>
            <strong>{t('app.name')}</strong>
            <p>{isLender ? t('auth.lenderPortal') : t('app.tagline')}</p>
          </div>
        </div>

        <h1>{isLender ? t('auth.lenderSignIn') : t('auth.signIn')}</h1>

        {error && <ErrorBanner message={error} />}

        <form onSubmit={submit} className="stacked-form">
          <label>
            {t('auth.email')}
            <input
              type="email"
              value={email}
              required
              autoComplete="email"
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label>
            {t('auth.password')}
            <input
              type="password"
              value={password}
              required
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <button className="primary-button wide" type="submit" disabled={busy}>
            {busy ? <InlineSpinner /> : <LogIn size={15} strokeWidth={2} aria-hidden="true" />}
            {t('auth.signIn')}
          </button>
        </form>

        <div className="auth-footer">
          {!isLender && (
            <p>
              {t('auth.noAccount')} <Link to="/sign-up">{t('auth.signUp')}</Link>
            </p>
          )}
          <p>
            <Link to={isLender ? '/sign-in' : '/lender/sign-in'}>
              {isLender ? t('auth.workerPortal') : t('auth.lenderPortal')}
            </Link>
          </p>
        </div>

        {/* Language is offered before sign-in, because someone who cannot read
            the form cannot reach the setting that would fix it. */}
        <div className="language-row" role="group" aria-label={t('auth.language')}>
          {LANGUAGES.map((entry) => (
            <button
              key={entry.code}
              type="button"
              className={`chip${language === entry.code ? ' active' : ''}`}
              onClick={() => setLanguage(entry.code as LanguageCode)}
            >
              {entry.native}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
