'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';

import { useAuth } from '@/lib/auth';
import type { AuthUser } from '@/lib/types';

/** The signed-in account pill: shows the user's initial and opens a small menu
 *  with their email and a logout action. */
export default function AccountMenu({ user }: { user: AuthUser }) {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const label = user.display_name || user.email;
  const initial = label.charAt(0).toUpperCase();

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Account"
        className="flex h-9 w-9 items-center justify-center rounded-full bg-ink text-sm font-semibold text-white transition hover:brightness-125 active:scale-95"
      >
        {initial}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="absolute right-0 top-11 z-[60] w-56 overflow-hidden rounded-2xl bg-surface p-1.5 shadow-card ring-1 ring-black/[0.06]"
            initial={{ opacity: 0, scale: 0.96, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -6 }}
            transition={{ duration: 0.14 }}
          >
            <div className="px-3 py-2">
              {user.display_name && <p className="truncate text-sm font-medium text-ink">{user.display_name}</p>}
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
            <div className="my-1 h-px bg-hairline" />
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                void logout();
              }}
              className="w-full rounded-xl px-3 py-2 text-left text-sm text-ink transition hover:bg-surface-2"
            >
              Log out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
