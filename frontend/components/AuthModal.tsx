'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useState } from 'react';

import { requestPasswordReset } from '@/lib/api';
import { useAuth } from '@/lib/auth';

interface AuthModalProps {
  open: boolean;
  onClose: () => void;
}

type Mode = 'signin' | 'signup' | 'forgot';

/** Sign in / create account, plus "Continue with Google". Matches the app's
 *  light tokens and the framer-motion overlay pattern used elsewhere. */
export default function AuthModal({ open, onClose }: AuthModalProps) {
  const { login, register, loginWithGoogle, loginWithApple, canUseApple } = useAuth();
  const [mode, setMode] = useState<Mode>('signup');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'forgot') {
        await requestPasswordReset(email);
        setResetSent(true);
        return;
      }
      if (mode === 'signup') await register(email, password, name || undefined);
      else await login(email, password);
      onClose();
      setEmail('');
      setPassword('');
      setName('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const tab = (m: Mode, label: string) =>
    `flex-1 rounded-full px-4 py-1.5 text-sm font-medium transition ${
      mode === m ? 'bg-white text-ink shadow-soft ring-1 ring-black/[0.04]' : 'text-muted hover:text-ink'
    }`;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label="Sign in to NextWatch"
        >
          <motion.div
            className="w-full max-w-sm overflow-hidden rounded-3xl bg-surface p-6 shadow-card"
            initial={{ scale: 0.94, y: 12 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-1 flex items-center justify-between">
              <h2 className="text-xl font-semibold tracking-tight text-ink">
                {mode === 'signup' ? 'Create your account' : mode === 'forgot' ? 'Reset your password' : 'Welcome back'}
              </h2>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="flex h-8 w-8 items-center justify-center rounded-full text-muted transition hover:bg-surface-2 hover:text-ink"
              >
                ✕
              </button>
            </div>
            <p className="mb-4 text-sm text-muted">
              {mode === 'forgot'
                ? "Enter your email and we'll send you a reset link."
                : 'Save your watchlist and taste across devices.'}
            </p>

            {mode !== 'forgot' && (
              <>
                <div className="mb-4 flex items-center rounded-full bg-black/[0.04] p-0.5">
                  <button type="button" className={tab('signup', 'Sign up')} onClick={() => setMode('signup')}>
                    Sign up
                  </button>
                  <button type="button" className={tab('signin', 'Sign in')} onClick={() => setMode('signin')}>
                    Sign in
                  </button>
                </div>

                {canUseApple && (
                  <button
                    type="button"
                    onClick={() => {
                      setError(null);
                      loginWithApple()
                        .then(onClose)
                        .catch((err) =>
                          setError(err instanceof Error ? err.message : 'Apple sign-in failed. Try again.'),
                        );
                    }}
                    className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-black px-4 py-2.5 text-sm font-medium text-white transition hover:brightness-125 active:scale-[0.98]"
                  >
                    <span aria-hidden></span>
                    Continue with Apple
                  </button>
                )}
                <button
                  type="button"
                  onClick={loginWithGoogle}
                  className="mb-4 flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-ink ring-1 ring-black/[0.12] transition hover:bg-surface-2 active:scale-[0.98]"
                >
                  <GoogleGlyph />
                  Continue with Google
                </button>

                <div className="mb-4 flex items-center gap-3 text-xs text-faint">
                  <span className="h-px flex-1 bg-hairline" />
                  or
                  <span className="h-px flex-1 bg-hairline" />
                </div>
              </>
            )}

            {mode === 'forgot' && resetSent ? (
              <div className="space-y-4">
                <p className="text-sm text-ink">
                  If an account exists for <span className="font-medium">{email}</span>, a reset link is on its way.
                  Check your inbox.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setResetSent(false);
                    setMode('signin');
                  }}
                  className="w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-110 active:scale-[0.98]"
                >
                  Back to sign in
                </button>
              </div>
            ) : (
            <form onSubmit={submit} className="space-y-3">
              {mode === 'signup' && (
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Name (optional)"
                  autoComplete="name"
                  className="w-full rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none ring-1 ring-transparent transition focus:ring-accent"
                />
              )}
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
                autoComplete="email"
                className="w-full rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none ring-1 ring-transparent transition focus:ring-accent"
              />
              {mode !== 'forgot' && (
                <input
                  type="password"
                  required
                  minLength={mode === 'signup' ? 8 : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === 'signup' ? 'Password (8+ characters)' : 'Password'}
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                  className="w-full rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none ring-1 ring-transparent transition focus:ring-accent"
                />
              )}

              {error && <p className="text-sm text-pass">{error}</p>}

              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
              >
                {busy
                  ? 'Please wait…'
                  : mode === 'signup'
                    ? 'Create account'
                    : mode === 'forgot'
                      ? 'Send reset link'
                      : 'Sign in'}
              </button>

              {mode === 'signin' && (
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setMode('forgot');
                  }}
                  className="w-full text-center text-xs text-muted transition hover:text-ink"
                >
                  Forgot password?
                </button>
              )}
              {mode === 'forgot' && (
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setMode('signin');
                  }}
                  className="w-full text-center text-xs text-muted transition hover:text-ink"
                >
                  ← Back to sign in
                </button>
              )}
            </form>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Google "G" mark. */
function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}
