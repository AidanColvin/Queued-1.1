import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy — Queued',
  description: 'What Queued collects, how it is used, and how to delete your data.',
};

// Last reviewed date shown to users. Update when the policy materially changes.
const UPDATED = 'June 2026';
// TODO: set this to a real monitored address before App Store submission.
const CONTACT = 'privacy@queued.app';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-[17px] font-semibold tracking-tight text-ink">{title}</h2>
      <div className="space-y-2 text-[15px] leading-relaxed text-muted">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <main className="app-shell mx-auto flex w-full max-w-2xl flex-col">
      <header className="mb-6 flex items-center justify-between gap-2">
        <a href="/" className="text-sm font-medium text-muted transition hover:text-ink">
          ← Back
        </a>
        <span className="text-[17px] font-semibold tracking-tight text-ink">Privacy</span>
        <span className="w-12" aria-hidden />
      </header>

      <div className="space-y-7 pb-10">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Queued Privacy Policy</h1>
          <p className="mt-1 text-sm text-faint">Last updated {UPDATED}</p>
        </div>

        <p className="text-[15px] leading-relaxed text-muted">
          Queued is a movie and TV recommendation app. This policy explains exactly what we collect,
          why, and how you can remove it. We do not sell your data, show third-party ads, or track you
          across other apps or websites.
        </p>

        <Section title="What we collect">
          <ul className="list-disc space-y-1.5 pl-5">
            <li>
              <strong className="text-ink">Account details</strong> — if you create an account: your
              email address and display name. Sign in with Apple or Google share only your email and
              name with us.
            </li>
            <li>
              <strong className="text-ink">Your taste activity</strong> — the titles you swipe (like,
              dislike, save, &ldquo;not seen&rdquo;), your watchlist, and any ratings you import from
              Letterboxd. This is what powers your recommendations.
            </li>
            <li>
              <strong className="text-ink">An anonymous session id</strong> — a random id stored on
              your device so guests get personalized picks before signing in. It is not linked to your
              identity.
            </li>
          </ul>
        </Section>

        <Section title="How we use it">
          <p>
            Your swipes and saved titles are used solely to generate and improve the recommendations
            you see. Email and name are used to sign you in and sync your watchlist across devices. We
            do not use your data for advertising and we do not run any third-party trackers, so the app
            shows no App Tracking Transparency prompt.
          </p>
        </Section>

        <Section title="Deleting your data">
          <p>
            You can permanently delete your account at any time from the account menu
            (&ldquo;Delete account&rdquo;). This removes your profile, watchlist, swipe history,
            imported ratings, and streaming preferences from our servers. Guests can clear local data
            by signing out or clearing the app&rsquo;s storage.
          </p>
        </Section>

        <Section title="Data sources & attribution">
          <p>
            Recommendations are produced by a model trained on public, non-commercial datasets
            (MovieLens). Posters, cast, and overviews come from{' '}
            <a className="text-accent hover:underline" href="https://www.themoviedb.org">
              TMDB
            </a>
            ; streaming availability is provided by JustWatch via TMDB. Queued is not endorsed or
            certified by TMDB.
          </p>
        </Section>

        <Section title="Children">
          <p>Queued is not directed at children under 13 and does not knowingly collect their data.</p>
        </Section>

        <Section title="Contact">
          <p>
            Questions or data requests:{' '}
            <a className="text-accent hover:underline" href={`mailto:${CONTACT}`}>
              {CONTACT}
            </a>
            .
          </p>
        </Section>
      </div>
    </main>
  );
}
