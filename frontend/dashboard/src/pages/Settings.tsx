/**
 * Profile and language.
 *
 * Language is saved to the account rather than only to this browser, so it
 * follows the person to a new device. Email and role are shown but not editable:
 * one is the account identity, the other decides which half of the product a
 * person sees, and neither is a preference.
 */

import { useEffect, useState } from 'react';
import { Check, Save } from 'lucide-react';
import { useAuth } from '@/auth/AuthContext';
import { LANGUAGES, useI18n } from '@/i18n';
import { useAction } from '@/lib/useAsync';
import { formatDate } from '@/lib/format';
import { Card, ErrorBanner, InlineSpinner, PageHeader } from '@/components/primitives';
import type { LanguageCode } from '@/i18n';

export default function Settings() {
  const { user, updateProfile } = useAuth();
  const { t, language, setLanguage } = useI18n();
  const save = useAction(updateProfile);

  const [form, setForm] = useState({
    name: user?.name ?? '',
    phone: user?.phone ?? '',
    employment_type: user?.employment_type ?? '',
    date_of_birth: user?.date_of_birth ?? '',
  });
  const [saved, setSaved] = useState(false);

  // The confirmation is transient by design: a permanent "Saved." next to a
  // form the reader has since edited is a lie.
  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 3000);
    return () => window.clearTimeout(timer);
  }, [saved]);

  if (!user) return null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const result = await save.run({
      name: form.name || undefined,
      phone: form.phone || undefined,
      employment_type: form.employment_type || undefined,
      date_of_birth: form.date_of_birth || undefined,
      language: language as LanguageCode,
    });
    if (result) setSaved(true);
  };

  const chooseLanguage = async (code: LanguageCode) => {
    setLanguage(code);
    // Persisted immediately rather than waiting for Save: the reader has just
    // changed the language of the button they would have to press.
    const result = await save.run({ language: code });
    if (result) setSaved(true);
  };

  return (
    <>
      <PageHeader eyebrow={t('nav.settings')} title={t('settings.title')} />

      <Card title={t('auth.language')} kicker={t('settings.languageHelp')}>
        <div className="language-row" role="group" aria-label={t('auth.language')}>
          {LANGUAGES.map((entry) => (
            <button
              key={entry.code}
              type="button"
              className={`chip${language === entry.code ? ' active' : ''}`}
              onClick={() => void chooseLanguage(entry.code as LanguageCode)}
            >
              {entry.native}
            </button>
          ))}
        </div>
      </Card>

      <Card title={t('settings.profile')}>
        {save.error && <ErrorBanner message={save.error} />}
        {saved && (
          <div className="banner tone-positive" role="status">
            <Check size={15} strokeWidth={2} aria-hidden="true" />
            <span>{t('settings.saved')}</span>
          </div>
        )}

        <form onSubmit={submit} className="stacked-form">
          <div className="form-grid">
            <label>
              {t('auth.name')}
              <input
                value={form.name}
                onChange={(event) => setForm((c) => ({ ...c, name: event.target.value }))}
              />
            </label>
            <label>
              {t('auth.phone')}
              <input
                type="tel"
                value={form.phone}
                onChange={(event) => setForm((c) => ({ ...c, phone: event.target.value }))}
              />
            </label>
          </div>

          <div className="form-grid">
            <label>
              {t('auth.dob')}
              <input
                type="date"
                value={form.date_of_birth}
                onChange={(event) => setForm((c) => ({ ...c, date_of_birth: event.target.value }))}
              />
              <small>{t('auth.dobHelp')}</small>
            </label>
            <label>
              {t('auth.employment')}
              <input
                value={form.employment_type}
                onChange={(event) =>
                  setForm((c) => ({ ...c, employment_type: event.target.value }))
                }
              />
              <small>{t('auth.employmentHelp')}</small>
            </label>
          </div>

          <dl className="field-list">
            <div className="field-row">
              <dt>{t('auth.email')}</dt>
              <dd>{user.email}</dd>
            </div>
            <div className="field-row">
              <dt>{t('auth.signUp')}</dt>
              <dd>{formatDate(user.created_at)}</dd>
            </div>
          </dl>

          <button className="primary-button" type="submit" disabled={save.busy}>
            {save.busy ? <InlineSpinner /> : <Save size={15} strokeWidth={2} aria-hidden="true" />}
            {t('action.save')}
          </button>
        </form>
      </Card>
    </>
  );
}
