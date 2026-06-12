'use client';

import { motion } from 'framer-motion';

interface WelcomeGateProps {
  /** Open the sign-in / create-account modal (Google, Apple in-app, email). */
  onSignIn: () => void;
  /** Continue without an account — remembered for this browser session. */
  onGuest: () => void;
}

/**
 * Sign-in screen between the wordmark splash and the deck: one quiet page
 * offering sign-in (Google / Apple / email+password via the auth modal) or
 * guest browsing. Shown to every signed-out visitor once per browser session;
 * picking guest mode or signing in dismisses it (sessionStorage).
 */
export default function WelcomeGate({ onSignIn, onGuest }: WelcomeGateProps) {
  return (
    <motion.div
      className="flex flex-1 flex-col items-center justify-center gap-8 text-center"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Queued</h1>
        <p className="text-[15px] text-muted">
          Swipe through films. It learns your taste — every swipe makes the next pick better.
        </p>
      </div>

      <div className="flex w-full max-w-xs flex-col gap-3">
        <button
          type="button"
          onClick={onSignIn}
          className="rounded-full bg-ink px-6 py-3 text-[15px] font-medium text-white transition hover:brightness-125 active:scale-95"
        >
          Sign in or create account
        </button>
        <button
          type="button"
          onClick={onGuest}
          className="rounded-full px-6 py-3 text-[15px] font-medium text-muted transition hover:text-ink active:scale-95"
        >
          Browse as guest →
        </button>
      </div>

      <p className="max-w-xs text-xs text-faint">
        An account keeps your watchlist and taste profile across devices. Guests can sign in any
        time — nothing is lost.
      </p>
    </motion.div>
  );
}
