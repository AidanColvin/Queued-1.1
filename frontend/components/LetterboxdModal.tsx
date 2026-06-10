'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';

import { getLetterboxdStatus, importLetterboxd, syncLetterboxd } from '@/lib/api';
import type { LetterboxdStatus, LetterboxdSummary } from '@/lib/types';

interface LetterboxdModalProps {
  open: boolean;
  onClose: () => void;
  /** Fired after a successful import so the deck can adopt the new likes/seen. */
  onImported?: () => void;
}

/** Connect a Letterboxd account: sync the public RSS diary by username, or
 *  upload the full data export (ZIP / ratings.csv / watched.csv). */
export default function LetterboxdModal({ open, onClose, onImported }: LetterboxdModalProps) {
  const [status, setStatus] = useState<LetterboxdStatus | null>(null);
  const [username, setUsername] = useState('');
  const [summary, setSummary] = useState<LetterboxdSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'sync' | 'upload' | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setSummary(null);
    setError(null);
    getLetterboxdStatus()
      .then((s) => {
        setStatus(s);
        if (s.username) setUsername(s.username);
      })
      .catch(() => setStatus(null));
  }, [open]);

  const finish = (result: LetterboxdSummary) => {
    setSummary(result);
    if (result.liked || result.seen) onImported?.();
    getLetterboxdStatus().then(setStatus).catch(() => {});
  };

  const sync = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return;
    setBusy('sync');
    setError(null);
    setSummary(null);
    try {
      finish(await syncLetterboxd(username.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed. Try again.');
    } finally {
      setBusy(null);
    }
  };

  const upload = async (file: File) => {
    setBusy('upload');
    setError(null);
    setSummary(null);
    try {
      finish(await importLetterboxd(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed. Try again.');
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

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
          aria-label="Connect Letterboxd"
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
              <h2 className="text-xl font-semibold tracking-tight text-ink">Connect Letterboxd</h2>
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
              Your ratings become taste signals: films you loved seed recommendations, and everything you&apos;ve
              watched stops showing up in the deck.
            </p>

            {status?.username && (
              <p className="mb-3 text-xs text-muted">
                Connected as <span className="font-medium text-ink">@{status.username}</span> ·{' '}
                {status.matched}/{status.imported} films matched
              </p>
            )}

            <form onSubmit={sync} className="mb-4 flex gap-2">
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Letterboxd username"
                autoCapitalize="none"
                autoCorrect="off"
                className="min-w-0 flex-1 rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none ring-1 ring-transparent transition focus:ring-accent"
              />
              <button
                type="submit"
                disabled={busy !== null || !username.trim()}
                className="shrink-0 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
              >
                {busy === 'sync' ? 'Syncing…' : 'Sync'}
              </button>
            </form>
            <p className="-mt-2 mb-4 text-[11px] text-faint">
              Reads your public RSS diary (most recent ~50 entries). Private profiles can use the export upload
              below.
            </p>

            <div className="mb-4 flex items-center gap-3 text-xs text-faint">
              <span className="h-px flex-1 bg-hairline" />
              or upload your export
              <span className="h-px flex-1 bg-hairline" />
            </div>

            <input
              ref={fileRef}
              type="file"
              accept=".zip,.csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f);
              }}
            />
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-ink ring-1 ring-black/[0.12] transition hover:bg-surface-2 active:scale-[0.98] disabled:opacity-50"
            >
              {busy === 'upload' ? 'Importing…' : 'Choose ZIP or CSV…'}
            </button>
            <p className="mt-2 text-[11px] text-faint">
              Letterboxd → Settings → Data → Export your data. Upload the ZIP (or just ratings.csv / watched.csv)
              for your full history.
            </p>

            {error && <p className="mt-3 text-sm text-pass">{error}</p>}

            {summary && (
              <div className="mt-4 rounded-2xl bg-surface-2 p-3 text-sm text-ink">
                <p className="font-medium">
                  Imported {summary.matched} of {summary.total} films
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {summary.liked} new like{summary.liked === 1 ? '' : 's'} · {summary.seen} marked seen
                  {summary.unmatched.length > 0 && ` · ${summary.unmatched.length} not in our catalog`}
                </p>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
