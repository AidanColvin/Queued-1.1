'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import * as api from './api';
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
  /** Permanently delete the account and all of its data, then sign out. */
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Wraps the app and exposes auth state + actions via {@link useAuth}. The auth
 *  session itself is the httpOnly cookie; this only mirrors who that cookie is. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Resolve the current session once on mount (and after a Google redirect back).
  useEffect(() => {
    let cancelled = false;
    api
      .getMe()
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

  const login = useCallback(async (email: string, password: string) => {
    setUser(await api.login(email, password));
  }, []);

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    setUser(await api.register(email, password, displayName));
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  const loginWithGoogle = useCallback(() => {
    window.location.href = api.googleLoginUrl();
  }, []);

  const deleteAccount = useCallback(async () => {
    await api.deleteAccount();
    setUser(null); // the backend already cleared the cookie
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, loginWithGoogle, deleteAccount }}>
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
