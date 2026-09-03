/**
 * Session state: who is signed in, and how that changes.
 *
 * One provider owns the token and the profile, so no screen ever reads
 * localStorage directly and there is exactly one path in and out of a session.
 *
 * On first mount the stored token is verified against the server rather than
 * trusted: a token can be expired, revoked, or left behind by an account that
 * no longer exists, and showing a dashboard to any of those would be a lie the
 * first API call then contradicts.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { auth as authApi } from '@/lib/api';
import { getToken, onSessionExpired, setToken } from '@/lib/client';
import { useI18n } from '@/i18n';
import type { LanguageCode } from '@/i18n';
import type { ProfileUpdate, RegisterPayload, Role, UserProfile } from '@/lib/types';

type AuthValue = {
  user: UserProfile | null;
  /** True until the stored token has been checked, so guards do not bounce early. */
  initialising: boolean;
  signIn: (email: string, password: string, expectedRole?: Role) => Promise<UserProfile>;
  signUp: (payload: RegisterPayload) => Promise<UserProfile>;
  signOut: () => void;
  updateProfile: (changes: ProfileUpdate) => Promise<UserProfile>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [initialising, setInitialising] = useState(true);
  const { setLanguage } = useI18n();

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  /** Adopts a signed-in profile and switches the UI to that account's language. */
  const adopt = useCallback(
    (profile: UserProfile) => {
      setUser(profile);
      if (profile.language) setLanguage(profile.language as LanguageCode);
      return profile;
    },
    [setLanguage],
  );

  // A 401 from anywhere ends the session. Registered once, centrally, so an
  // expired token cannot leave one screen working and another silently empty.
  useEffect(() => onSessionExpired(signOut), [signOut]);

  useEffect(() => {
    if (!getToken()) {
      setInitialising(false);
      return;
    }

    let cancelled = false;
    authApi
      .me()
      .then((profile) => {
        if (!cancelled) adopt(profile);
      })
      .catch(() => {
        // Any failure here means the token cannot be used. Clearing it is right
        // whether it expired or the backend is down: the app falls back to the
        // sign-in screen, which states the problem plainly when they try.
        if (!cancelled) signOut();
      })
      .finally(() => {
        if (!cancelled) setInitialising(false);
      });

    return () => {
      cancelled = true;
    };
  }, [adopt, signOut]);

  const signIn = useCallback(
    async (email: string, password: string, expectedRole?: Role) => {
      const result = await authApi.login(email, password, expectedRole);
      setToken(result.access_token);
      return adopt(result.user);
    },
    [adopt],
  );

  const signUp = useCallback(
    async (payload: RegisterPayload) => {
      const result = await authApi.register(payload);
      setToken(result.access_token);
      return adopt(result.user);
    },
    [adopt],
  );

  const updateProfile = useCallback(
    async (changes: ProfileUpdate) => adopt(await authApi.updateProfile(changes)),
    [adopt],
  );

  const value = useMemo<AuthValue>(
    () => ({ user, initialising, signIn, signUp, signOut, updateProfile }),
    [user, initialising, signIn, signUp, signOut, updateProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside an AuthProvider');
  return context;
}
