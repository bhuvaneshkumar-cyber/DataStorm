/**
 * Language context: one hook, `useI18n`, that every screen reads.
 *
 * The chosen language is stored on the account rather than in the browser, so
 * it follows a person to a new device. This provider keeps a local copy too, so
 * the sign-in and registration screens -- which run before there is an account
 * to read from -- can still be translated.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { DICTIONARIES, LANGUAGES, type LanguageCode, type StringKey } from './strings';

const STORAGE_KEY = 'gigsave.language';
const FALLBACK: LanguageCode = 'en';

type I18nValue = {
  language: LanguageCode;
  setLanguage: (code: LanguageCode) => void;
  /** Looks up a string, falling back to English and then to the key itself. */
  t: (key: StringKey) => string;
  languages: typeof LANGUAGES;
};

const I18nContext = createContext<I18nValue | null>(null);

function isSupported(value: string | null | undefined): value is LanguageCode {
  return !!value && LANGUAGES.some((entry) => entry.code === value);
}

function initialLanguage(): LanguageCode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isSupported(stored)) return stored;
  } catch {
    // Storage unavailable; fall through to the browser's own preference.
  }
  const browser = navigator.language?.split('-')[0];
  return isSupported(browser) ? browser : FALLBACK;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<LanguageCode>(initialLanguage);

  const setLanguage = useCallback((code: LanguageCode) => {
    setLanguageState(code);
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch {
      // The choice still applies to this session; it just will not be remembered.
    }
  }, []);

  // Keeps the document in step so screen readers announce content in the right
  // language and the browser offers the right spellchecker.
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo<I18nValue>(
    () => ({
      language,
      setLanguage,
      t: (key: StringKey) => DICTIONARIES[language][key] ?? DICTIONARIES[FALLBACK][key] ?? key,
      languages: LANGUAGES,
    }),
    [language, setLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used inside an I18nProvider');
  return context;
}

export type { LanguageCode, StringKey };
export { LANGUAGES };
