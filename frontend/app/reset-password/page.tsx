'use client';

import { useEffect, useState } from 'react';

import { resetPassword } from '@/lib/api';

/** Landing page for the emailed password-reset link
 *  (`/reset-password/?token=…`). Static-export friendly: the token is read
 *  from `window.location` after mount, never during prerender. */
export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get('token') ?? '');
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await resetPassword(token ?? '', password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell mx-auto flex w-full max-w-md flex-col items-center justify-center">
      <div className="w-full rounded-3xl bg-surface p-6 shadow-card">
        <h1 className="mb-1 text-xl font-semibold tracking-tight text-ink">Set a new password</h1>

        {token === null ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : !token ? (
          <p className="text-sm text-muted">
            This link is missing its token. Open the reset link from your email again.
          </p>
        ) : done ? (
          <div className="space-y-4">
            <p className="text-sm text-ink">Your password has been updated.</p>
            <a
              href="/"
              className="block w-full rounded-xl bg-accent px-4 py-2.5 text-center text-sm font-semibold text-white transition hover:brightness-110"
            >
              Back to Queued
            </a>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-4 space-y-3">
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="New password (8+ characters)"
              autoComplete="new-password"
              className="w-full rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none ring-1 ring-transparent transition focus:ring-accent"
            />
            <input
              type="password"
              required
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat new password"
              autoComplete="new-password"
              className="w-full rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none ring-1 ring-transparent transition focus:ring-accent"
            />
            {error && <p className="text-sm text-pass">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
            >
              {busy ? 'Please wait…' : 'Update password'}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
