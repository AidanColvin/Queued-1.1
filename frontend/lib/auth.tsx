'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import * as api from './api';
import { initAuthToken, isNative, nativeAppleSignIn, setAuthToken } from './native';
import type { AuthUser } from './types';

interface AuthContextValue {
  /** The signed-in user, or null when anonymous. */
  user: AuthUser | null;
  /** True until the initial /me check resolves (avoids an auth-state flash). */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Kick off the full-page Google OAuth redirect. */
  loginWithGoogle: () => void;
  /** Native Sign in with Apple (Capacitor builds only — see canUseApple). */
  loginWithApple: () => Promise<void>;
  /** Whether the Apple sign-in button should be offered (native shell). */
  canUseApple: boolean;
  /** Permanently delete the account and all of its data, then sign out. */
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Wraps the app and exposes auth state + actions via {@link useAuth}. The auth
 *  session itself is the httpOnly cookie; this only mirrors who that cookie is. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Resolve the current session once on mount (and after a Google redirect
  // back). On native, the stored bearer token must load before the /me call.
  useEffect(() => {
    let cancelled = false;
    initAuthToken()
      .then(() => api.getMe())
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Adopt a fresh session: persist the bearer token for the native shell
  // (no-op on the web, where the httpOnly cookie is the session).
  const adopt = useCallback(async (u: AuthUser) => {
    if (u.access_token) await setAuthToken(u.access_token);
    setUser({ ...u, access_token: null }); // never keep the token in React state
  }, []);

  const login = useCallback(
    async (email: string, password: string) => adopt(await api.login(email, password)),
    [adopt],
  );

  const register = useCallback(
    async (email: string, password: string, displayName?: string) =>
      adopt(await api.register(email, password, displayName)),
    [adopt],
  );

  const logout = useCallback(async () => {
    await api.logout();
    await setAuthToken(null);
    setUser(null);
  }, []);

  const loginWithGoogle = useCallback(() => {
    window.location.href = api.googleLoginUrl();
  }, []);

  const loginWithApple = useCallback(async () => {
    const { identityToken, displayName } = await nativeAppleSignIn();
    await adopt(await api.appleSignIn(identityToken, displayName));
  }, [adopt]);

  const deleteAccount = useCallback(async () => {
    await api.deleteAccount();
    await setAuthToken(null);
    setUser(null); // the backend already cleared the cookie
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        logout,
        loginWithGoogle,
        loginWithApple,
        canUseApple: isNative(),
        deleteAccount,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/** Access auth state + actions. Must be used under an {@link AuthProvider}. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
