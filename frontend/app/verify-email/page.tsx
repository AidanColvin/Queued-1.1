'use client';

import { useEffect, useState } from 'react';

import { verifyEmail } from '@/lib/api';

/** Landing page for the emailed verification link (`/verify-email/?token=…`).
 *  Posts the token once on mount and shows the outcome. */
export default function VerifyEmailPage() {
  const [status, setStatus] = useState<'working' | 'ok' | 'error'>('working');

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token');
    if (!token) {
      setStatus('error');
      return;
    }
    verifyEmail(token)
      .then(() => setStatus('ok'))
      .catch(() => setStatus('error'));
  }, []);

  return (
    <main className="app-shell mx-auto flex w-full max-w-md flex-col items-center justify-center">
      <div className="w-full rounded-3xl bg-surface p-6 text-center shadow-card">
        {status === 'working' && <p className="text-sm text-muted">Confirming your email…</p>}
        {status === 'ok' && (
          <>
            <h1 className="mb-1 text-xl font-semibold tracking-tight text-ink">Email confirmed ✓</h1>
            <p className="mb-4 text-sm text-muted">Thanks — your account is verified.</p>
          </>
        )}
        {status === 'error' && (
          <>
            <h1 className="mb-1 text-xl font-semibold tracking-tight text-ink">Link expired</h1>
            <p className="mb-4 text-sm text-muted">
              This verification link is invalid or has expired. Sign in and request a new one.
            </p>
          </>
        )}
        {status !== 'working' && (
          <a
            href="/"
            className="block w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-110"
          >
            Back to Queued
          </a>
        )}
      </div>
    </main>
  );
}
