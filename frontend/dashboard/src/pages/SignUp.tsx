/**
 * Registration.
 *
 * Two fields are optional but visible: date of birth and what the person does.
 * Both feed the credit score, and both are asked for here with the reason
 * stated, rather than being demanded later at the moment someone is trying to
 * borrow money.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldCheck, UserPlus } from 'lucide-react';
import { useAuth } from '@/auth/AuthContext';
import { HOME_FOR } from '@/auth/ProtectedRoute';
import { LANGUAGES, useI18n } from '@/i18n';
import { useAction } from '@/lib/useAsync';
import { ErrorBanner, InlineSpinner } from '@/components/primitives';
import type { LanguageCode } from '@/i18n';
import type { Role } from '@/lib/types';

const MIN_PASSWORD_LENGTH = 8;

export default function SignUp() {
  const { signUp } = useAuth();
  const { t, language, setLanguage } = useI18n();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    phone: '',
    employment_type: '',
    date_of_birth: '',
    role: 'worker' as Role,
  });
  const { run, busy, error } = useAction(signUp);

  const update = (field: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const user = await run({
      name: form.name,
      email: form.email,
      password: form.password,
      language,
      role: form.role,
      // Empty optional fields are omitted rather than sent as "", which the API
      // would reject as a malformed date or store as a blank job description.
      ...(form.phone ? { phone: form.phone } : {}),
      ...(form.employment_type ? { employment_type: form.employment_type } : {}),
      ...(form.date_of_birth ? { date_of_birth: form.date_of_birth } : {}),
    });
    if (user) navigate(HOME_FOR[user.role], { replace: true });
  };

  return (
    <div className="auth-page">
      <div className="auth-card wide">
        <div className="auth-brand">
          <span className="brand-symbol" aria-hidden="true">
            <ShieldCheck size={18} strokeWidth={2.4} />
          </span>
          <div>
            <strong>{t('app.name')}</strong>
            <p>{t('app.tagline')}</p>
          </div>
        </div>

        <h1>{t('auth.signUp')}</h1>

        {error && <ErrorBanner message={error} />}

        <form onSubmit={submit} className="stacked-form">
          <label>
            {t('auth.name')}
            <input value={form.name} required autoComplete="name" onChange={update('name')} />
          </label>

          <div className="form-grid">
            <label>
              {t('auth.email')}
              <input
                type="email"
                value={form.email}
                required
                autoComplete="email"
                onChange={update('email')}
              />
            </label>
            <label>
              {t('auth.phone')}
              <input
                type="tel"
                value={form.phone}
                autoComplete="tel"
                onChange={update('phone')}
              />
            </label>
          </div>

          <label>
            {t('auth.password')}
            <input
              type="password"
              value={form.password}
              required
              minLength={MIN_PASSWORD_LENGTH}
              autoComplete="new-password"
              onChange={update('password')}
            />
            <small>{t('auth.passwordHelp')}</small>
          </label>

          <div className="form-grid">
            <label>
              {t('auth.dob')}
              {/* A native date input: it localises, validates and offers a
                  picker without a dependency. */}
              <input type="date" value={form.date_of_birth} onChange={update('date_of_birth')} />
              <small>{t('auth.dobHelp')}</small>
            </label>
            <label>
              {t('auth.employment')}
              <input
                value={form.employment_type}
                onChange={update('employment_type')}
                placeholder="Swiggy delivery partner"
              />
              <small>{t('auth.employmentHelp')}</small>
            </label>
          </div>

          <fieldset className="role-picker">
            <legend>{t('auth.signUp')}</legend>
            {(['worker', 'lender'] as Role[]).map((option) => (
              <label key={option} className={`role-option${form.role === option ? ' active' : ''}`}>
                <input
                  type="radio"
                  name="role"
                  value={option}
                  checked={form.role === option}
                  onChange={() => setForm((current) => ({ ...current, role: option }))}
                />
                {option === 'worker' ? t('auth.workerPortal') : t('auth.lenderPortal')}
              </label>
            ))}
          </fieldset>

          <button className="primary-button wide" type="submit" disabled={busy}>
            {busy ? <InlineSpinner /> : <UserPlus size={15} strokeWidth={2} aria-hidden="true" />}
            {t('auth.signUp')}
          </button>
        </form>

        <div className="auth-footer">
          <p>
            {t('auth.haveAccount')} <Link to="/sign-in">{t('auth.signIn')}</Link>
          </p>
        </div>

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
